"""
Minimal copy of the three text helpers the frontend imports from the full
project's YourIndexingAI.modules.modules_utils. Kept byte-for-byte identical in
behaviour so the chat rendering matches the original.
"""
import re


def process_table(input_string, n=None):
    pattern = r'```TABLE(.*?)```'
    output_string = re.sub(pattern, '', input_string, flags=re.DOTALL)
    return output_string


def replace_expection(text):
    # take TABLE out because it is already on the left table
    text = process_table(text)
    # Step 1: Replace INFOTABLE blocks with placeholders
    code_block_pattern = r'```INFOTABLE(.*?)```'
    code_blocks = re.findall(code_block_pattern, text, re.DOTALL)

    placeholder_pattern = r'__CODE_BLOCK_{}__'
    placeholders = {i: placeholder_pattern.format(i) for i in range(len(code_blocks))}

    for i, block in enumerate(code_blocks):
        text = text.replace(f'```INFOTABLE{block}```', placeholders[i])

    text = re.sub(r'^.*DATATABLE.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^.*DATATOPLOT.*$', '', text, flags=re.MULTILINE)
    # Step 2: Replace \n with <br> outside code blocks
    text = text.replace('\n', '<br>')

    # Step 3: Restore the original code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(placeholders[i], f'{block}\n\n')

    return text


def extract_tag_content(text, tag_name):
    """Extract content between <tag_name>...</tag_name>, or None."""
    pattern = f"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None
