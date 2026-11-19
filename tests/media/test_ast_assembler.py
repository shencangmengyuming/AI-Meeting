from app.media.domain.transcription import AstTranscriptionAssembler


def test_ast_assembler_replaces_partial_segment_and_derives_live_text() -> None:
    assembler = AstTranscriptionAssembler()

    first = assembler.apply(segment_id=1, text="hello", finalized=False)
    second = assembler.apply(segment_id=1, text="hello world", finalized=False)

    assert first.full_text == "hello"
    assert second.full_text == "hello world"
    assert second.committed_text == ""
    assert second.live_text == "hello world"


def test_ast_assembler_keeps_finalized_text_stable_and_appends_punctuation() -> None:
    assembler = AstTranscriptionAssembler()

    assembler.apply(segment_id=1, text="hello world", finalized=True)
    update = assembler.apply(segment_id=1, text=".", finalized=False)

    assert update.full_text == "hello world."
    assert update.committed_text == "hello world."
    assert update.live_text == ""


def test_ast_assembler_no_pgs_reuses_range_and_removes_covered_sibling() -> None:
    assembler = AstTranscriptionAssembler()
    assembler.apply(
        segment_id=1, bg=0, ed=1200, text="我今天想和大家", finalized=False
    )
    assembler.apply(segment_id=2, bg=1200, ed=2100, text="聊一下", finalized=False)
    assembler.apply(
        segment_id=3, bg=2100, ed=3400, text="实时转写", finalized=False
    )

    update = assembler.apply(
        segment_id=4,
        bg=1200,
        ed=3400,
        text="聊一下实时转写",
        finalized=False,
    )
    punctuation = assembler.apply(
        segment_id=5, bg=1200, ed=3400, text="。", finalized=False
    )

    assert update.full_text == "我今天想和大家聊一下实时转写"
    assert punctuation.full_text == "我今天想和大家聊一下实时转写。"


def test_ast_assembler_rpl_removes_declared_segment_range() -> None:
    assembler = AstTranscriptionAssembler()
    assembler.apply(segment_id=1, pgs="apd", text="hello ", finalized=False)
    assembler.apply(segment_id=2, pgs="apd", text="world", finalized=False)

    update = assembler.apply(
        segment_id=3,
        pgs="rpl",
        rg=(1, 2),
        text="hi",
        finalized=True,
    )

    assert update.full_text == "hi"
    assert update.committed_text == "hi"
    assert update.live_text == ""
