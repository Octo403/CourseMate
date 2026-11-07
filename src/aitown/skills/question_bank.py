from .base import Skill
from ..question_bank.models import GetArgs, QuestionResult, SearchArgs, SolveArgs, StatusArgs, StatusResult


class QuestionSearch(Skill):
    name = 'question_search'
    description = '只读课程题库：按课程、知识点、年份和题型找真实题目。未准备时报告 needs_preparation，不下载，不查个人库。顶层 question_ids 可绑定 question_get。'
    arguments = SearchArgs
    result_type = QuestionResult

    def __init__(self, bank):
        self.bank = bank

    def run(self, arguments):
        return self.bank.search(arguments)


class QuestionGet(Skill):
    name = 'question_get'
    description = '批量读取本会话实际题目 ID 的完整原题、图表和出处。include_answer 默认 false；仅用户明确要答案时开启，返回已有来源答案，绝不生成替代答案。'
    arguments = GetArgs
    result_type = QuestionResult

    def __init__(self, bank):
        self.bank = bank

    def run(self, arguments):
        return self.bank.get(arguments)


class CourseStatus(Skill):
    name = 'course_status'
    description = '只读查询指定课程题库的真实准备任务、进度、失败数和覆盖范围。'
    arguments = StatusArgs
    result_type = StatusResult

    def __init__(self, bank):
        self.bank = bank

    def run(self, arguments):
        return self.bank.status(arguments.course)


class QuestionSolve(Skill):
    name = 'question_solve'
    description = '解答本会话选中的一道原题，返回 ChatGPT 书面参考解答及方法归纳；不改变用户的做题标记。'
    arguments = SolveArgs
    result_type = QuestionResult

    def __init__(self, bank):
        self.bank = bank

    def run(self, arguments):
        from ..question_bank.solve import solve_question
        return solve_question(self.bank, arguments.question_id)
