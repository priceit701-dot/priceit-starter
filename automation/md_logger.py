#!/usr/bin/env python3
import json, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
POLICY = BASE / 'md_logger_policy.json'
STATE = BASE / 'md_logger_state.json'


def now():
    return datetime.datetime.now()


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def append_md(path: Path, heading: str, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = now().isoformat(timespec='seconds')
    block = [f"\n## {heading} ({ts})\n"]
    for ln in lines:
        block.append(f"- {ln}\n")
    with path.open('a', encoding='utf-8') as f:
        f.writelines(block)


def rotate_daily_memory(mem_dir: Path):
    d = now().strftime('%Y-%m-%d')
    return mem_dir / f'{d}.md'


def main():
    policy = load_json(POLICY, {
        'enabled': True,
        'default_md': '/Users/sanghun/.openclaw/workspace/priceit-starter/docs/WORKLOG.md',
        'memory_dir': '/Users/sanghun/.openclaw/workspace/memory',
        'mode': 'idle',
        'heading': '자동 기록',
        'lines': []
    })
    state = load_json(STATE, {'last_run': None, 'last_heading': None})

    if not policy.get('enabled', True):
        return

    mode = policy.get('mode', 'idle')
    heading = policy.get('heading', '자동 기록')
    lines = policy.get('lines') or ['(내용 없음)']

    if mode == 'memory-daily':
        target = rotate_daily_memory(Path(policy.get('memory_dir')))
    else:
        target = Path(policy.get('default_md'))

    append_md(target, heading, lines)

    state['last_run'] = now().isoformat(timespec='seconds')
    state['last_heading'] = heading
    save_json(STATE, state)


if __name__ == '__main__':
    main()
