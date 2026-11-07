from copy import deepcopy

import pytest

from aitown.question_bank.models import COURSE_ID
from aitown.question_bank.parts import focus_question, saved_parts, selection_parts, validate_parts


@pytest.fixture
def section(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    path = tmp_path/'section.pdf'
    with fitz.open() as document:
        page = document.new_page(width=400, height=500)
        for y, text in [(40, 'Instructions'), (80, '1. Matching'), (180, '2. Planar graph'), (280, '3. Partial order')]:
            page.insert_text((40, y), text)
        page = document.new_page(width=400, height=500)
        page.insert_text((40, 80), '4. Symmetric and transitive closure')
        page.insert_text((40, 105), '(R union inverse R)+')
        page.insert_text((40, 200), 'Next major question')
        document.save(path)
    question = {'id': 7, 'course_id': COURSE_ID, 'number': '一', 'content_format': 'image',
                'text': '一、判断并说明理由\n1. Matching\n2. Planar graph\n3. Partial order\n4. Symmetric and transitive closure\n(R union inverse R)+',
                'images': ['page1.png', 'page2.png'], 'missing': [], 'topics': ['匹配', '平面图', '偏序', '关系'],
                'image_regions': [{'index': 0, 'page': 1, 'bbox': [0, 20, 400, 320]},
                                  {'index': 1, 'page': 2, 'bbox': [0, 60, 400, 120]}],
                'source_pages': [{'ordinal': 1}, {'ordinal': 2}]}
    question['selection_parts'] = selection_parts(question)
    return question, path


def test_only_matched_item_is_cropped_with_formula_and_shared_instruction(section):
    import pymupdf as fitz
    question, path = section
    original = deepcopy(question)
    focus_question(question, ['4'], path)
    assert question['text'] == original['text'] and question['id'] == 7
    assert question['display_number'] == '一 · 第4小题'
    assert question['match_instruction'] == '一、判断并说明理由'
    assert question['images'] == ['page2.png']
    assert question['source_pages'] == [{'ordinal': 2}]
    assert len(question['image_previews']) == 1
    preview = question['image_previews'][0]
    with fitz.open(path) as document:
        text = document[preview['page']-1].get_text(clip=fitz.Rect(preview['bbox']))
    assert '4. Symmetric' in text and '(R union inverse R)+' in text
    assert all(word not in text for word in ('Matching', 'Planar', 'Partial', 'Next major'))


def test_multiple_matches_keep_separate_crops_and_exclude_middle_siblings(section):
    question, path = section
    focus_question(question, ['1', '4'], path)
    assert [p['part'] for p in question['image_previews']] == ['1', '4']
    assert [p['page'] for p in question['image_previews']] == [1, 2]
    assert question['image_previews'][0]['bbox'][3] < 120


def test_old_reason_recovers_exact_item_but_dependent_proof_stays_whole(section):
    question, _ = section
    assert saved_parts(question, {'match_reason': '第4小题直接考查对称性。'}) == ['4']
    assert saved_parts(question, {'match_reason': '第四小问直接考查对称性。'}) == ['4']
    assert saved_parts(question, {'match_reason': '属于关系性质。'}) == []
    assert selection_parts({'text': '一、证明下列结论\n1. First\n2. Using part 1'}) == []
    with pytest.raises(ValueError):
        validate_parts(question, ['5'])
    with pytest.raises(ValueError):
        validate_parts(question, ['4', '4'])


def test_unlocatable_crop_does_not_show_unrelated_siblings(section):
    question, _ = section
    focus_question(question, ['4'])
    assert question['images'] == [] and question['image_previews'] == []
    assert question['source_pages'] == [{'ordinal': 1}, {'ordinal': 2}]
    assert '边界暂无法确认' in question['missing'][-1]
