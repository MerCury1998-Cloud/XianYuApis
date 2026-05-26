"""
update_price_prompt.py
读取 Switch 代理价格表 Markdown 文件，解析价格规则，
更新 goofish_live.py 中的 LLM_SYSTEM_PROMPT 使其包含价格信息。
"""

import re
import os

# 价格表路径
PRICE_FILE = r'C:\Users\Administrator\WorkBuddy\2026-05-25-10-56-30\Switch代理价格表.md'
LIVE_FILE = os.path.join(os.path.dirname(__file__), 'goofish_live.py')


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
        '【Switch 游戏机闲鱼自动客服 - 价格信息】',
        '',
        '你是Switch游戏机卖家的闲鱼AI客服。回答客户问题时，请参考以下价格信息：',
        '',
    ]

    for sec in sections:
        if not sec['rows']:
            continue
        lines.append(f'■ {sec["title"]}')
        for row in sec['rows']:
            if 'retail_price' in row:
                lines.append(f'  - {row["config"]}：拿货价{row["price"]}元，建议零售价{row["retail_price"]}元')
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
        '- 用亲切、热情的语气回答客户问题',
        '- 回答要简短直接',
        '- 如果客户询价，根据上面的价格表给出建议零售价',
        '- 如果客户问及配置差异，如实介绍',
        '- 不要使用表情符号',
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
