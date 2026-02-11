#!/usr/bin/env python3
import json
import time
import subprocess
import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
POLICY = BASE / 'policy.json'
STATE = BASE / 'state.json'
LOG = BASE / 'loop_log.jsonl'

FAIL_CODES = {
    'NO_NEXT_STEP': 'NO_NEXT_STEP',
    'NO_EVIDENCE': 'NO_EVIDENCE',
    'INVALID_EVIDENCE_JSON': 'INVALID_EVIDENCE_JSON',
    'MISSING_EVIDENCE_FIELDS': 'MISSING_EVIDENCE_FIELDS',
    'INVALID_EVIDENCE_STATUS': 'INVALID_EVIDENCE_STATUS',
    'ROUTE_DEVIATION': 'ROUTE_DEVIATION',
    'EXECUTOR_NOT_CONFIGURED': 'EXECUTOR_NOT_CONFIGURED',
    'EXECUTOR_NONZERO': 'EXECUTOR_NONZERO',
    'EVIDENCE_FAIL_COUNT_MISMATCH': 'EVIDENCE_FAIL_COUNT_MISMATCH',
}

REQUIRED_EVIDENCE_FIELDS = {'step', 'status', 'checks', 'failed', 'proof_ts'}


def now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def log(event):
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')


def parse_evidence(stdout: str, token: str):
    if token not in stdout:
        return None, FAIL_CODES['NO_EVIDENCE']
    tail = stdout.split(token, 1)[1].strip()
    line = tail.splitlines()[0].strip()
    if not line:
        return None, FAIL_CODES['NO_EVIDENCE']
    try:
        payload = json.loads(line)
    except Exception:
        return None, FAIL_CODES['INVALID_EVIDENCE_JSON']
    if not REQUIRED_EVIDENCE_FIELDS.issubset(set(payload.keys())):
        return payload, FAIL_CODES['MISSING_EVIDENCE_FIELDS']
    if payload.get('status') not in {'PASS', 'FAIL'}:
        return payload, FAIL_CODES['INVALID_EVIDENCE_STATUS']
    return payload, None


def planner(policy):
    runbook = Path(policy.get('runbook_path', 'docs/kakao-openchat-export-runbook.md'))
    exists = runbook.exists()
    return {'ok': exists, 'runbook': str(runbook), 'ts': now()}


def executor(policy):
    mode = policy.get('mode', 'normal')
    mode_cmd_map = {
        'normal': (policy.get('executor_command') or '').strip(),
        'downgrade': (policy.get('executor_command_downgrade') or '').strip(),
        'hold': '',
    }
    cmd = mode_cmd_map.get(mode, mode_cmd_map['normal'])

    if mode == 'hold':
        return {'ok': False, 'code': 'HOLD_MODE', 'stdout': '', 'stderr': 'controller in hold mode', 'rc': None}
    if not cmd:
        return {'ok': False, 'code': FAIL_CODES['EXECUTOR_NOT_CONFIGURED'], 'stdout': '', 'stderr': '', 'rc': None}

    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return {
        'ok': p.returncode == 0,
        'rc': p.returncode,
        'stdout': (p.stdout or '').strip(),
        'stderr': (p.stderr or '').strip(),
        'cmd': cmd,
        'mode': mode,
    }


def validator(policy, exec_result):
    if not exec_result.get('ok'):
        return {'pass': False, 'code': exec_result.get('code') or FAIL_CODES['EXECUTOR_NONZERO'], 'evidence': None}

    out = exec_result.get('stdout', '')
    must_next = policy.get('require_next_step_token', 'NEXT_STEP_OK')
    must_evidence = policy.get('require_evidence_token', 'EVIDENCE:')

    if must_next and must_next not in out:
        return {'pass': False, 'code': FAIL_CODES['NO_NEXT_STEP'], 'evidence': None}
    evidence, err = parse_evidence(out, must_evidence)
    if err:
        return {'pass': False, 'code': err, 'evidence': evidence}
    if 'ROUTE_CHANGED' in out:
        return {'pass': False, 'code': FAIL_CODES['ROUTE_DEVIATION'], 'evidence': evidence}

    failed = int(evidence.get('failed', 0))
    status = evidence.get('status')
    if status == 'PASS' and failed != 0:
        return {'pass': False, 'code': FAIL_CODES['EVIDENCE_FAIL_COUNT_MISMATCH'], 'evidence': evidence}
    if status == 'FAIL' and failed == 0:
        return {'pass': False, 'code': FAIL_CODES['EVIDENCE_FAIL_COUNT_MISMATCH'], 'evidence': evidence}

    return {'pass': status == 'PASS', 'code': status, 'evidence': evidence}


def patcher(state, val):
    state.setdefault('fail_streak', 0)
    state.setdefault('mode', 'normal')

    if val.get('pass'):
        state['retry_count'] = 0
        state['fail_streak'] = 0
        state['last_fail_code'] = None
        state['last_pass_at'] = now()
        if state.get('mode') != 'hold':
            state['mode'] = 'normal'
        return state

    state['last_fail_code'] = val.get('code')
    state['retry_count'] = state.get('retry_count', 0) + 1
    state['fail_streak'] = state.get('fail_streak', 0) + 1
    return state


def apply_mode_policy(policy, state):
    downgrade_after = int(policy.get('downgrade_after_failures', 2))
    hold_after = int(policy.get('hold_after_failures', 5))
    fail_streak = int(state.get('fail_streak', 0))

    prev_mode = state.get('mode', 'normal')
    if fail_streak >= hold_after:
        state['mode'] = 'hold'
    elif fail_streak >= downgrade_after:
        state['mode'] = 'downgrade'
    elif fail_streak == 0:
        state['mode'] = 'normal'

    return {'previous_mode': prev_mode, 'new_mode': state.get('mode', 'normal')}


def recover(policy, state):
    max_retry = int(policy.get('max_retry', 3))
    if state.get('retry_count', 0) < max_retry:
        return {'triggered': False}
    cmd = (policy.get('recovery_command') or '').strip()
    if not cmd:
        return {'triggered': False, 'reason': 'recovery_command_not_configured'}
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    state['retry_count'] = 0
    return {
        'triggered': True,
        'rc': p.returncode,
        'stdout': (p.stdout or '').strip()[:300],
        'stderr': (p.stderr or '').strip()[:200],
    }


def main():
    state = load_json(STATE, {'enabled': True, 'retry_count': 0, 'mode': 'normal', 'fail_streak': 0})
    save_json(STATE, state)
    while True:
        policy = load_json(POLICY, {})
        state = load_json(STATE, {'enabled': True, 'retry_count': 0, 'mode': 'normal', 'fail_streak': 0})
        policy['mode'] = state.get('mode', 'normal')

        if not state.get('enabled', True):
            log({'ts': now(), 'phase': 'paused'})
            time.sleep(2)
            continue

        plan = planner(policy)
        ex = executor(policy)
        val = validator(policy, ex)
        status = 'success' if val.get('pass') else 'fail'

        state = patcher(state, val)
        mode_change = apply_mode_policy(policy, state)
        recovery = recover(policy, state) if not val.get('pass') else {'triggered': False}
        save_json(STATE, state)

        evt = {
            'ts': now(),
            'status': status,
            'plan': plan,
            'validator': val,
            'executor': {
                'rc': ex.get('rc'),
                'mode': ex.get('mode', state.get('mode')),
                'cmd': ex.get('cmd', ''),
                'stdout': ex.get('stdout', '')[:500],
                'stderr': ex.get('stderr', '')[:300],
            },
            'state': {
                'retry_count': state.get('retry_count', 0),
                'last_fail_code': state.get('last_fail_code'),
                'fail_streak': state.get('fail_streak', 0),
                'mode': state.get('mode', 'normal'),
            },
            'mode_change': mode_change,
            'recovery': recovery,
        }
        log(evt)

        time.sleep(float(policy.get('cycle_sec', 5)))


if __name__ == '__main__':
    main()
