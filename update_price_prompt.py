"""
update_price_prompt.py
读取 Switch 代理价格表 Markdown 文件，解析价格规则，
更新 goofish_live.py 中的 LLM_SYSTEM_PROMPT 使其包含价格信息。
"""

import re
import os
import json
import hashlib
import requests

# 价格表路径
PRICE_FILE = r'C:\Users\Administrator\WorkBuddy\2026-05-25-10-56-30\Switch代理价格表.md'
LIVE_FILE = os.path.join(os.path.dirname(__file__), 'goofish_live.py')
STATE_FILE = os.path.join(os.path.dirname(__file__), '.price_state.json')
FEISHU_WEBHOOK = 'https://open.feishu.cn/open-apis/bot/v2/hook/52fa6601-ac5b-4a04-9a34-0ca1033e3237'


def send_feishu(title, content):
    """发送飞书通知"""
    try:
        session = requests.Session()
        session.trust_env = False
        resp = session.post(FEISHU_WEBHOOK, json={
            "msg_type": "text",
            "content": {"text": f"{title}\n{content}"}
        }, timeout=10)
        if resp.status_code == 200:
            print(f'✅ 飞书通知已发送')
        else:
            print(f'⚠️ 飞书通知返回异常: {resp.status_code}')
    except Exception as e:
        print(f'⚠️ 飞书通知失败: {e}')


def load_state():
    """加载上次价格状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_state(state):
    """保存当前价格状态"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def compute_price_hash(md_text):
    """计算价格表内容的 MD5 哈希"""
    return hashlib.md5(md_text.encode('utf-8')).hexdigest()


def check_and_notify(md_text):
    """检查价格是否有变动，有变动则飞书通知并返回 True"""
    state = load_state()
    new_hash = compute_price_hash(md_text)
    old_hash = state.get('hash')
    if old_hash == new_hash:
        print('✅ 价格无变动，跳过通知')
        return False
    if old_hash:
        changed_items = detect_changes(state.get('sections', []), md_text)
        if changed_items:
            msg = '📦 价格有变动：\n' + '\n'.join(changed_items)
        else:
            msg = '📦 价格表已更新（非价格项变动）'
        send_feishu('💰 价格表更新提醒', msg)
    save_state({'hash': new_hash, 'sections': md_text})
    return True


def detect_changes(old_md, new_md):
    """对比新旧价格表，返回变动的项目列表"""
    import difflib
    diff = list(difflib.unified_diff(
        old_md.splitlines(keepends=True),
        new_md.splitlines(keepends=True),
        fromfile='旧价格表', tofile='新价格表'
    ))
    changed = []
    for line in diff:
        if line.startswith('+') and not line.startswith('+++') and len(line) > 2:
            changed.append(line[1:].strip())
        elif line.startswith('-') and not line.startswith('---') and len(line) > 2:
            changed.append('删除: ' + line[1:].strip())
    return changed[:20]  # 最多20条





def parse_price_table(md_text):
    """解析价格表 markdown，返回结构化数据"""
    sections = []
    current_section = None

    for line in md_text.split('\n'):
        # 匹配标题行如 "## Switch 普通版 日/港版"
        head_match = re.match(r'^##\s+(.+)$', line.strip())
        if head_match:
            if current_section:
                sections.append(current_section)
            current_section = {'title': head_match.group(1), 'rows': []}
            continue

        # 匹配价格行（带 | 的分隔行，且最后一个字段是数字）
        if current_section and line.strip().startswith('|'):
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) < 2:
                continue
            # 确认最后一段是数字（价格行）
            last_has_price = re.search(r'[\d.]+', parts[-1])
            if not last_has_price:
                continue
            # 跳过表头
            if parts[0] in ['配置', '配件']:
                continue
            # 普通价格行（3列以上）：| 配置 | 拿货价 | 建议零售价 |
            if len(parts) >= 3:
                price1 = re.search(r'[\d.]+', parts[-2])
                price2 = re.search(r'[\d.]+', parts[-1])
                if price1 and price2:
                    current_section['rows'].append({
                        'config': parts[-3],
                        'price': price1.group(),
                        'retail_price': price2.group()
                    })
                    continue
            # 单列价格：| 配件 | 价格 |
            if len(parts) == 2:
                current_section['rows'].append({
                    'config': parts[0],
                    'price': last_has_price.group()
                })

    if current_section:
        sections.append(current_section)

    return sections


def build_price_prompt(sections):
    """将解析后的价格数据格式化为自然语言价格说明"""
    lines = [
        '【Switch 游戏机价格表】',
        '',
        '你是闲鱼客服，我们这里主要经营Switch游戏机。回答客户问题时，请参考以下价格：',
        '',
    ]

    for sec in sections:
        if not sec['rows']:
            continue
        lines.append(f'■ {sec["title"]}')
        for row in sec['rows']:
            if 'retail_price' in row:
                lines.append(f'  - {row["config"]}：{row["retail_price"]}元')
            else:
                lines.append(f'  - {row["config"]}：{row["price"]}元')
        lines.append('')

    lines += [
        '【注意事项】',
        '- 所有机器均为双系统（正版+破解）',
        '- 顺丰包邮，河南周口发货',
        '- 闲鱼禁止词：破解、动森、动物之森、生化危机、微信等，回复时避免使用这些词汇',
        '',
        '回答要求：',
        '- 用朋友聊天的语气，随意简短，不要过度热情假客气',
        '- 回答要简短直接，不要啰嗦',
        '- 如果客户询价，根据上面的价格表直接报价',
        '- 如果客户问及配置差异，如实介绍',
        '- 如果客人问"机器哪年的"、"哪年的"、"年份"这种泛泛的问题，只准说"OLED款是25年的哦~"，禁止多说任何其他内容',
        '- 如果客人明确问"普通款哪年的"/"普通版哪年的"，回答"普通款是19年的哦"',
        '- 如果客人明确问"续航款哪年的"/"续航版哪年的"，回答"续航款是22/23年的哦"',
        '- 如果客人说转人工、人工之类的，回复"好的，稍等帮您联系~"然后发飞书通知我',
        '- 用俏皮的语气聊天，可以加颜文字和emoji，比如喵~ ^_^ 之类的',
        '- 不用刻意避开表情符号和淘宝味称呼',
    ]

    return '\n'.join(lines)


def update_system_prompt(new_prompt):
    """更新 goofish_live.py 中的 LLM_SYSTEM_PROMPT"""
    with open(LIVE_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # 尝试三引号格式
    matcher = re.search(r"(LLM_SYSTEM_PROMPT\s*=\s*)'''(.+?)'''", content, re.DOTALL)
    quote_style = "'''"  # 三引号
    if not matcher:
        # 尝试单引号格式
        matcher = re.search(r"(LLM_SYSTEM_PROMPT\s*=\s*)'(.*?)'", content, re.DOTALL)
        quote_style = "'"
    if not matcher:
        print('错误：未找到 LLM_SYSTEM_PROMPT')
        return False

    prefix = matcher.group(1)
    old_prompt = matcher.group(2)
    # 转义提示词中的引号
    escaped_prompt = new_prompt.replace(quote_style, '\\' + quote_style)
    # 构造旧字符串和新字符串，确保精确匹配
    old_str = f"{prefix}{quote_style}{old_prompt}{quote_style}"
    new_str = f"{prefix}{quote_style}{escaped_prompt}{quote_style}"
    if old_str not in content:
        print('错误：匹配到了正则但替换字符串未找到（格式意外）')
        return False
    content = content.replace(old_str, new_str, 1)

    with open(LIVE_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

    return True

    with open(LIVE_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

    return True


def main():
    print(f'📖 读取价格表: {PRICE_FILE}')
    with open(PRICE_FILE, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # 检查价格是否有变动，有变动则飞书通知
    check_and_notify(md_text)

    sections = parse_price_table(md_text)
    print(f'✅ 解析到 {len(sections)} 个价格分类')

    for sec in sections:
        print(f'   {sec["title"]}: {len(sec["rows"])} 条价格规则')

    new_prompt = build_price_prompt(sections)
    print('\n📝 新 SYSTEM_PROMPT 预览:')
    print(new_prompt[:200] + '...\n')

    if update_system_prompt(new_prompt):
        print(f'✅ 已更新 {LIVE_FILE} 中的 LLM_SYSTEM_PROMPT')
    else:
        print('❌ 更新失败')
        return

    # 验证
    with open(LIVE_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    v_match = re.search(r"LLM_SYSTEM_PROMPT\s*=\s*'''(.+?)'''", content, re.DOTALL)
    if not v_match:
        v_match = re.search(r"LLM_SYSTEM_PROMPT\s*=\s*'(.*?)'", content, re.DOTALL)
    if v_match:
        prompt_len = len(v_match.group(1))
        print(f'✅ 验证通过：LLM_SYSTEM_PROMPT 长度 = {prompt_len} 字符')


if __name__ == '__main__':
    main()
