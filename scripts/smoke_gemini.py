"""One real recording, at most four Gemini requests, no business row/queue writes."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services/backend'))


def run(call_id, output, max_audio_seconds):
    from app.ai.gemini import limited_requests
    from app.ai.workflows import daily_coaching_summary, grade_call, romanize_segments
    from app.appwrite import repos
    from app.config.settings import get_settings
    from app.jazz.downloader import verify_audio
    from app.jobs.worker import _download_storage_to_tmp
    from app.reporting.compute import compute_report
    from app.transcription.service import assign_roles, transcribe_file
    settings = get_settings()
    call = repos.get_doc('calls', call_id)
    if not call or not call.get('recording_storage_file_id') or call.get('recording_deleted_at'):
        raise RuntimeError('Choose a call with a retained real recording.')
    models = {key: getattr(settings, key) for key in (
        'GEMINI_TRANSCRIBE_MODEL', 'GEMINI_ROMANIZER_MODEL', 'GEMINI_GRADING_MODEL')}
    result = json.loads(output.read_text()) if output.exists() else {
        'call_id': call_id, 'recording_sha256': call.get('recording_sha256'),
        'models': models, 'max_audio_seconds': max_audio_seconds,
        'generation_requests': 0, 'existing_calls_and_grades_modified': False,
    }
    if (result['call_id'] != call_id or result['models'] != models
            or result['recording_sha256'] != call.get('recording_sha256')
            or result['max_audio_seconds'] != max_audio_seconds):
        raise RuntimeError('Checkpoint does not match recording/models; choose a fresh output path.')
    output.parent.mkdir(parents=True, exist_ok=True)
    def checkpoint():
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(result, file, indent=2, ensure_ascii=False)
    with limited_requests(4) as budget:
        try:
            if 'segments' not in result:
                with tempfile.TemporaryDirectory(prefix='gemini-smoke-') as directory:
                    source = _download_storage_to_tmp(call, Path(directory))
                    clip = Path(directory) / 'test.mp3'
                    subprocess.run(['ffmpeg', '-y', '-i', str(source), '-t', str(max_audio_seconds),
                                    '-ac', '1', '-ar', '16000', '-b:a', '64k', str(clip)],
                                   check=True, capture_output=True, timeout=120)
                    duration = verify_audio(clip)['duration']
                    print('Testing one recording:', call_id, 'audio seconds:', round(duration, 2), flush=True)
                    raw = assign_roles(transcribe_file(clip), call.get('jazz_agent_identifier', ''))
                if not raw:
                    raise RuntimeError('Selected recording had no speech; no grades were fabricated.')
                result['tested_audio_seconds'] = duration
                result['original_audio_seconds'] = call.get('duration_seconds')
                result['segments'] = [{'id': 'seg_' + str(i), 'speaker_raw': item['speaker'], 'speaker_role': item['role'],
                             'start_seconds': item['start'], 'end_seconds': item['end'],
                             'raw_text': item['text'], 'uncertain': item['uncertain']}
                            for i, item in enumerate(raw)]
                checkpoint()
                print('Transcription passed:', len(result['segments']), 'turns,', len({s['speaker_raw'] for s in result['segments']}), 'speakers.', flush=True)
            if not result.get('romanization_done'):
                result['segments'] = romanize_segments(result['segments'])
                result['romanization_done'] = True
                checkpoint()
                print('Roman Urdu passed: segment IDs and timing preserved.', flush=True)
            if 'grade' not in result:
                rules = '\n'.join(row['key'] + ': ' + row['value'] for row in repos.list_docs('business_rules', limit=50))
                result['grade'] = grade_call(result['segments'], {'direction': call.get('direction'),
                                   'duration_seconds': result['tested_audio_seconds'],
                                   'agent': call.get('agent_name_snapshot'), 'customer': 'REDACTED'}, rules)
                checkpoint()
                print('Structured grading passed. Weighted score:', result['grade']['overall_score'], flush=True)
            if 'coaching' not in result:
                metrics = compute_report([{**call, 'pipeline_status': 'COMPLETE'}], {call_id: result['grade']})
                result['coaching'] = daily_coaching_summary(metrics, [result['grade']])
                checkpoint()
                print('Daily coaching passed.', flush=True)
            result['status'] = 'COMPLETE'
        except Exception as exc:
            from app.ai.gemini import GeminiError
            result["status"] = "INCOMPLETE"
            result["last_error"] = str(exc) if isinstance(exc, GeminiError) else type(exc).__name__
            raise
        finally:
            result['generation_requests'] += budget['used']
            checkpoint()
            write_report(result, output)
    print('Total checkpointed Gemini requests:', result['generation_requests'], flush=True)
    print('Private test report:', output.with_suffix('.md'), flush=True)
    return result


def write_report(result, output):
    content = '# Gemini real-call test\n\n'
    content += f'Status: **{result.get("status", "INCOMPLETE")}** · requests in this checkpoint: {result["generation_requests"]}\n\n'
    content += 'Existing call results were preserved. Speaker roles are heuristic assignments; review them against the recording.\n\n'
    if result.get('last_error') and result.get('status') != 'COMPLETE':
        content += 'Provider error: ' + result['last_error'] + '\n\n'
    if result.get('grade'):
        grade = result['grade']
        content += f'## Grade\n\nScore: {grade["overall_score"]}\n\n{grade["analysis"]}\n\n{grade["coaching_summary"]}\n\n'
    content += '## Transcript\n\n'
    for segment in result.get('segments', []):
        text = segment.get('roman_urdu_text') or segment['raw_text']
        content += f'- **{segment["speaker_raw"]} / {segment["speaker_role"]} [{segment["start_seconds"]:.1f}–{segment["end_seconds"]:.1f}s]** {text}\n'
    if result.get('coaching'):
        content += '\n## Daily coaching sample\n\n' + result['coaching'] + '\n'
    fd = os.open(output.with_suffix('.md'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--call-id', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.verification/gemini-smoke.json')
    parser.add_argument('--max-audio-seconds', type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.max_audio_seconds <= 600:
        raise SystemExit('Use 1–600 seconds for the bounded smoke test.')
    try:
        run(args.call_id, args.output, args.max_audio_seconds)
    except Exception as exc:
        # Never print SDK/HTTP tracebacks containing credentials or cookies.
        from app.ai.gemini import GeminiError
        if isinstance(exc, GeminiError):
            raise SystemExit(str(exc)) from None
        raise SystemExit('Gemini smoke test failed (' + type(exc).__name__ + ').') from None


if __name__ == '__main__':
    main()
