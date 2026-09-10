"""Layer 2 tests for the YouTube URL helpers."""

import pytest
from django.core.exceptions import ValidationError

from api.utils.youtube import extract_video_id, validate_youtube_url

VIDEO_ID = "dQw4w9WgXcQ"


class TestExtractVideoId:
    @pytest.mark.parametrize(
        "url",
        [
            f"https://www.youtube.com/watch?v={VIDEO_ID}",
            f"https://youtu.be/{VIDEO_ID}",
            f"https://www.youtube.com/embed/{VIDEO_ID}",
            f"https://m.youtube.com/watch?v={VIDEO_ID}&feature=share",
        ],
    )
    def test_extracts_the_same_id_from_every_shape(self, url):
        assert extract_video_id(url) == VIDEO_ID

    @pytest.mark.parametrize(
        "url",
        [
            "https://vimeo.com/123456789",
            "https://example.com/watch?v=abc",
            "not a url",
            "https://www.youtube.com/watch?v=tooShort",
            "",
            None,
            # A matching host on a dangerous scheme must never pass (stored XSS).
            f"javascript://youtube.com/watch?v={VIDEO_ID}",
            f"data://youtu.be/{VIDEO_ID}",
        ],
    )
    def test_rejects_non_youtube_or_malformed(self, url):
        assert extract_video_id(url) is None


class TestValidateYoutubeUrl:
    def test_returns_id_for_a_valid_url(self):
        assert validate_youtube_url(f"https://youtu.be/{VIDEO_ID}") == VIDEO_ID

    def test_raises_for_a_non_youtube_url(self):
        with pytest.raises(ValidationError):
            validate_youtube_url("https://vimeo.com/1")
