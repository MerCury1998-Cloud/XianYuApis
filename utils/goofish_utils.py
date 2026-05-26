import base64
import json
import os
import subprocess
from functools import partial

import blackboxprotobuf

subprocess.Popen = partial(subprocess.Popen, encoding="utf-8")

_JS_FILE = os.path.join(os.path.dirname(__file__), '..', 'static', 'goofish_js_version_2.js')
_NODE = os.environ.get('NODE_PATH') or 'node'


def _call_js(func_name, *args):
    """通过 Node.js 子进程调用 JS 函数（读取 JS 文件 + 附加调用代码）"""
    with open(_JS_FILE, 'r', encoding='utf-8') as f:
        js_code = f.read()

    # 构造参数调用代码
    args_js = ', '.join(json.dumps(a) for a in args)
    call_code = f'''
const result = {func_name}({args_js});
console.log(JSON.stringify(result));
'''
    full_code = js_code + call_code

    try:
        proc = subprocess.run(
            [_NODE, '-e', full_code],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(_JS_FILE)
        )
        if proc.returncode != 0:
            raise RuntimeError(f'Node.js error: {proc.stderr.strip()}')
        out = proc.stdout.strip()
        return json.loads(out)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'JS function {func_name} timed out')


def trans_cookies(cookies_str):
    cookies = dict()
    for i in cookies_str.split("; "):
        try:
            cookies[i.split('=')[0]] = '='.join(i.split('=')[1:])
        except:
            continue
    return cookies


def trans_cookies_str(cookies_dict):
    cookies_str = ''
    for key, value in cookies_dict.items():
        cookies_str += f"{key}={value}; "
    return cookies_str[:-2]


def get_session_cookies(session):
    cookies = session.cookies.get_dict()
    return cookies


def get_session_cookies_str(session):
    cookies = session.cookies.get_dict()
    cookies_str = ''
    for key, value in cookies.items():
        cookies_str += f"{key}={value}; "
    return cookies_str[:-2]


def generate_mid():
    return _call_js('generate_mid')


def generate_uuid():
    return _call_js('generate_uuid')


def generate_device_id(user_id):
    return _call_js('generate_device_id', user_id)


def generate_sign(t, token, data):
    return _call_js('generate_sign', t, token, data)


def decrypt(data):
    return _call_js('decrypt', data)


if __name__ == '__main__':
    t = 1741667630548
    token = 'b7e897bf9767618a32b439c6103fe1cb'
    data = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"ED4CBA2C-5DA0-4154-A902-BF5CB52409E2-3888777108"}'
    print(generate_sign(t, token, data))
