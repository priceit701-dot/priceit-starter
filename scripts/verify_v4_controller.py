import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automation.controller import validator

policy = {
    'require_next_step_token': 'NEXT_STEP_OK',
    'require_evidence_token': 'EVIDENCE:'
}

ok_result = {
    'ok': True,
    'stdout': 'NEXT_STEP_OK\nEVIDENCE:{"step":"collect","status":"PASS","count":12}'
}
fail_result = {
    'ok': True,
    'stdout': 'NEXT_STEP_OK\nEVIDENCE:not-json'
}

v1 = validator(policy, ok_result)
v2 = validator(policy, fail_result)

print('V4_PASS', v1)
print('V4_FAIL', v2)
