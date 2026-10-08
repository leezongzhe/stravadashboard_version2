import unittest
from unittest.mock import patch

from app.ai_provider import generate_analysis, list_models


class AIProviderTests(unittest.TestCase):
    @patch("app.ai_provider._request_json")
    def test_gemini_text_and_model_parsing(self, request_json):
        request_json.side_effect = [
            {
                "models": [
                    {"name": "models/gemini-test", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embed-test", "supportedGenerationMethods": ["embedContent"]},
                ]
            },
            {"candidates": [{"content": {"parts": [{"text": "Measured analysis"}]}}]},
        ]
        self.assertEqual(list_models("gemini", "secret"), ["gemini-test"])
        answer = generate_analysis("gemini", "secret", "gemini-test", {"today": "2026-10-08"})
        self.assertEqual(answer, "Measured analysis")
        sent_payload = request_json.call_args.args[3]
        self.assertIn("today", sent_payload["contents"][0]["parts"][0]["text"])

    @patch("app.ai_provider._request_json")
    def test_openai_compatible_parsing(self, request_json):
        request_json.return_value = {"choices": [{"message": {"content": "Local answer"}}]}
        answer = generate_analysis(
            "openai_compatible", "secret", "local-model", {"today": "2026-10-08"},
            custom_base_url="http://localhost:1234/v1",
        )
        self.assertEqual(answer, "Local answer")
        self.assertEqual(request_json.call_args.args[1], "http://localhost:1234/v1/chat/completions")

    def test_remote_custom_provider_requires_https(self):
        with self.assertRaisesRegex(Exception, "must use HTTPS"):
            generate_analysis(
                "openai_compatible", "secret", "model", {},
                custom_base_url="http://example.com/v1",
            )


if __name__ == "__main__":
    unittest.main()
