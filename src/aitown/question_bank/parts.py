"""Locate independent numbered items inside a shared exam section."""
import re


ITEM = re.compile(r'^\s*(\d{1,2})[.．、](?!\d)\s*\S', re.MULTILINE)


def selection_parts(question):
    text = question.get('rendered_text') or question['text']
    # Dependent proof/calculation subparts retain their complete shared stem.
    if not re.search(r'判断|选择|填空', text.splitlines()[0] if text else ''):
        return []
    headings = list(ITEM.finditer(text))
    if len(headings) < 2 or [int(m[1]) for m in headings] != list(range(1, len(headings)+1)):
        return []
    return [{'number': m[1], 'text': text[m.start():headings[i+1].start() if i+1<len(headings) else len(text)].strip()}
            for i, m in enumerate(headings)]


def validate_parts(question, numbers):
    known = {p['number'] for p in question.get('selection_parts', selection_parts(question))}
    if len(numbers) != len(set(numbers)) or not set(numbers) <= known:
        raise ValueError('模型返回了不存在或重复的小题号')


def saved_parts(question, saved):
    """Old replies sometimes identified a subquestion only in the explanation."""
    if saved.get('matched_subquestions'):
        numbers = saved['matched_subquestions']
    else:
        chinese = dict(zip('一二三四五六七八九', map(str, range(1, 10))))
        numbers = list(dict.fromkeys(chinese.get(n, n) for n in re.findall(
            r'第\s*([1-9]\d?|[一二三四五六七八九])\s*(?:小题|小问)', saved.get('match_reason', ''))))
    known = {p['number'] for p in question.get('selection_parts', [])}
    return [n for n in numbers if n in known]


def focus_question(question, numbers, pdf_path=None):
    """Project a result onto matched items; source IDs and full stems survive."""
    validate_parts(question, numbers)
    if not numbers:
        return
    question['matched_subquestions'] = numbers
    question['display_number'] = question['number']+' · 第'+'、'.join(numbers)+'小题'
    chosen = [p for p in question['selection_parts'] if p['number'] in numbers]
    instruction = (question.get('rendered_text') or question['text']).splitlines()[0]
    question['match_instruction'] = instruction
    question['matched_text'] = instruction+'\n'+'\n'.join(p['text'] for p in chosen)
    from .prepare import labels
    question['topics'] = labels('\n'.join(p['text'] for p in chosen), question['course_id'])[0]
    if question['content_format'] != 'image':
        return
    try:
        regions = locate_parts(question, numbers, pdf_path)
    except (OSError, ValueError, RuntimeError):
        regions = []
    original_images = question['images']
    question['images'] = [original_images[r['original_index']] for r in regions]
    question['image_previews'] = [{**r, 'index': i, 'kind': 'crop', 'location_kind': 'page'} for i, r in enumerate(regions)]
    question['image_regions'] = [{'index': i, 'page': r['page'], 'bbox': r['bbox']} for i, r in enumerate(regions)]
    if regions:
        question['source_pages'] = [p for p in question['source_pages'] if p['ordinal'] in {r['page'] for r in regions}]
    else:
        question['missing'] = [*question['missing'], '命中小题的截图边界暂无法确认，请打开原页核对']


def locate_parts(question, numbers, pdf_path):
    import pymupdf as fitz
    if not pdf_path:
        return []
    regions = question['image_regions']
    headings, rows = [], []
    with fitz.open(pdf_path) as document:
        for region in regions:
            if not region.get('bbox'):
                return []
            page = document[region['page']-1]
            clip = fitz.Rect(region['bbox'])
            for block in page.get_text('dict', sort=True)['blocks']:
                for line in block.get('lines', []):
                    box = fitz.Rect(line['bbox'])
                    text = ''.join(s['text'] for s in line['spans']).strip()
                    if not text or not clip.intersects(box):
                        continue
                    # Omit the vertical binding margin and printed page footer.
                    if box.x1 < page.rect.width*.12 or re.match(r'^第\s*\d+\s*页', text):
                        continue
                    row = (region['index'], region['page'], box, text)
                    rows.append(row)
                    match = ITEM.match(text)
                    if match:
                        headings.append((match[1], row))
        if [n for n, _ in headings] != [p['number'] for p in question['selection_parts']]:
            return []
        result = []
        for position, (number, start) in enumerate(headings):
            if number not in numbers:
                continue
            stop = headings[position+1][1] if position+1<len(headings) else None
            # Same-baseline equation fragments belong to the numbered item even
            # when Word emitted them before its number in reading order.
            selected = [r for r in rows if (r[0], r[2].y1) >= (start[0], start[2].y0)
                        and (stop is None or (r[0], r[2].y0) < (stop[0], stop[2].y0-2))]
            for index in dict.fromkeys(r[0] for r in selected):
                segment = [r for r in selected if r[0] == index]
                source = next(r for r in regions if r['index'] == index)
                clip = fitz.Rect(source['bbox'])
                top = max(clip.y0, min(r[2].y0 for r in segment)-3)
                bottom = min(clip.y1, max(r[2].y1 for r in segment)+6)
                page = document[source['page']-1]
                # Preserve diagrams between this item and the following one.
                end = stop[2].y0-3 if stop and stop[0]==index else clip.y1
                objects = [fitz.Rect(d['rect']) for d in page.get_drawings()]
                objects += [fitz.Rect(i['bbox']) for i in page.get_image_info()]
                bottom = max([bottom, *[r.y1+3 for r in objects if r.y0>=top and r.y1<end
                              and r.x0>=clip.x0 and r.x1<=clip.x1 and r.height<page.rect.height*.9]])
                result.append({'original_index': index, 'page': source['page'], 'part': number,
                               'bbox': [clip.x0, top, clip.x1, min(bottom, end)],
                               'printed_label': source.get('printed_label')})
        return result
