from pathlib import Path

from matching import (
    build_output_name,
    mapping_entries_for_mode,
    match_all_videos,
    parse_mapping_rows,
    sort_video_files,
)
from watermark import sanitize_filename, text_similarity, _crf_to_bitrate


def test_parse_mapping_rows_tsv_three_columns():
    rows = parse_mapping_rows("1\t中文标题\tThis is the English caption\n2\t第二条\tAnother caption")
    assert rows == [
        {"seq": "1", "name": "中文标题", "caption": "This is the English caption"},
        {"seq": "2", "name": "第二条", "caption": "Another caption"},
    ]


def test_parse_mapping_rows_skips_header_and_continues_multiline_caption():
    rows = parse_mapping_rows("序号\t中文\t英文\n1\t标题\tFirst line\ncontinued line")
    assert len(rows) == 1
    assert rows[0]["seq"] == "1"
    assert rows[0]["name"] == "标题"
    assert rows[0]["caption"] == "First line\ncontinued line"


def test_parse_mapping_rows_csv_caption_with_commas():
    rows = parse_mapping_rows("1,标题,hello, world, again")
    assert rows[0] == {"seq": "1", "name": "标题", "caption": "hello,world,again"}


def test_mapping_entries_preserve_order_for_voice_or_order_and_sort_for_keyword():
    rows = [
        {"seq": "2", "name": "二", "caption": ""},
        {"seq": "1", "name": "一", "caption": ""},
    ]
    assert [r["seq"] for r in mapping_entries_for_mode(rows, match_by_order=True)] == ["2", "1"]
    assert [r["seq"] for r in mapping_entries_for_mode(rows)] == ["1", "2"]


def test_match_all_videos_exact_prefix_and_whole_token():
    videos = {
        "1": Path("1.mp4"),
        "2 intro": Path("2 intro.mp4"),
        "clip-3-final": Path("clip-3-final.mp4"),
        "clip13": Path("clip13.mp4"),
    }
    assert match_all_videos("1", videos) == [Path("1.mp4")]
    assert match_all_videos("2", videos) == [Path("2 intro.mp4")]
    assert match_all_videos("3", videos) == [Path("clip-3-final.mp4")]
    assert match_all_videos("13", videos) == []


def test_sort_video_files_by_name_default():
    videos = {"b": Path("b.mp4"), "a": Path("A.mp4")}
    assert sort_video_files(videos) == [Path("A.mp4"), Path("b.mp4")]


def test_build_output_name_adds_duplicate_index():
    name = build_output_name("7", "标题", Path("source.mov"), 2, 2, "水印-序号-中文标题")
    assert name == "水印-7-标题-2.mov"


def test_sanitize_filename_illegal_chars_reserved_and_truncation():
    assert sanitize_filename('bad/name:*?') == "bad_name"
    assert sanitize_filename("CON") == "CON_"
    long_name = "视频" * 100
    assert len(sanitize_filename(long_name, max_bytes=30).encode("utf-8")) <= 30


def test_text_similarity_obvious_match_and_mismatch():
    assert text_similarity("hello world", "hello world again") > 0.8
    assert text_similarity("apple banana", "car engine road") < 0.5


def test_crf_to_bitrate_sanity():
    high_quality = int(_crf_to_bitrate(18, 1080, 1920).rstrip("k"))
    smaller_file = int(_crf_to_bitrate(28, 1080, 1920).rstrip("k"))
    assert high_quality > smaller_file
    assert 1000 <= smaller_file <= 20000
