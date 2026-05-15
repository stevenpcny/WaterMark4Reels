from pathlib import Path

from processing import (
    build_process_items,
    detect_existing_outputs,
    infer_mime_type,
    make_result_row,
    result_to_job_record,
    split_existing_process_items,
    successful_upload_file_names,
    verify_output_folder_writable,
    write_caption_file,
    write_job_report,
)


def _row(seq="1", name="标题", caption="caption"):
    return {"seq": seq, "name": name, "caption": caption}


def test_build_process_items_respects_review_status(tmp_path):
    video = tmp_path / "1.mp4"
    video.write_text("x")

    def matched(_idx, _seq):
        return [video]

    def out_name(seq, name, vf, count, index):
        return f"out-{seq}{vf.suffix}"

    def review_id(idx, vf, output):
        return f"{idx}:{vf.name}:{output}"

    rows = [_row()]
    review_id_value = "0:1.mp4:out-1.mp4"
    assert build_process_items(rows, matched, out_name, review_id, {}, tmp_path, review_only_confirmed=True) == []
    items = build_process_items(
        rows,
        matched,
        out_name,
        review_id,
        {review_id_value: "confirmed"},
        tmp_path,
        review_only_confirmed=True,
    )
    assert len(items) == 1
    assert items[0]["output_file"] == tmp_path / "out-1.mp4"


def test_existing_split_and_caption_write(tmp_path):
    output = tmp_path / "out.mp4"
    output.write_text("video")
    item = {"row": _row(), "video_file": tmp_path / "in.mp4", "output_file": output}
    assert detect_existing_outputs([item], create_caption_files=True) == ["out.mp4"]
    pending, skipped = split_existing_process_items([item], create_caption_files=True)
    assert pending == [item]
    assert skipped == []

    ok, caption_name = write_caption_file(output, "hello")
    assert ok
    assert caption_name == "out.txt"
    pending, skipped = split_existing_process_items([item], create_caption_files=True)
    assert pending == []
    assert skipped == [item]


def test_reports_and_upload_names(tmp_path):
    item = {"row_index": 0, "row": _row(), "video_file": tmp_path / "in.mp4", "output_file": tmp_path / "out.mp4"}
    result = make_result_row(item, success=True, caption_file_name="out.txt", has_captions=True)
    record = result_to_job_record(item, result)
    job_path, csv_path = write_job_report(tmp_path, [record])
    assert job_path.exists()
    assert csv_path.exists()
    assert successful_upload_file_names([result]) == ["out.mp4", "out.txt"]


def test_infer_mime_type():
    assert infer_mime_type("a.mp4") == "video/mp4"
    assert infer_mime_type("a.mov") == "video/quicktime"
    assert infer_mime_type("a.txt") == "text/plain"
    assert infer_mime_type("a.unknownext") == "application/octet-stream"


def test_verify_output_folder_writable_uses_visible_temp_file(tmp_path):
    target = tmp_path / "成品文件夹"
    ok, error = verify_output_folder_writable(target)
    assert ok
    assert error == ""
    assert target.exists()
    assert not list(target.iterdir())
