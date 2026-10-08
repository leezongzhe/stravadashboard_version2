import unittest

from app.sync import _extract_activity_ids, _pagination_total, discover_activity_ids


class EmptyLocator:
    @property
    def first(self):
        return self

    async def count(self):
        return 0


class BodyLocator:
    def __init__(self, page):
        self.page = page

    async def inner_text(self):
        preceding = sum(len(items) for items in self.page.pages[:self.page.index])
        start = preceding + 1
        end = preceding + len(self.page.pages[self.page.index])
        return f"{start}-{end} of {sum(map(len, self.page.pages))}"


class NextLocator:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        return self

    async def count(self):
        return int(self.page.index < len(self.page.pages) - 1 and self.page.has_next)

    async def is_visible(self):
        return True

    async def is_enabled(self):
        return True

    async def get_attribute(self, _name):
        return None

    async def click(self):
        self.page.index += 1


class FakeTrainingPage:
    def __init__(self, pages, has_next=True):
        self.pages = pages
        self.index = 0
        self.has_next = has_next

    async def goto(self, *_args, **_kwargs):
        self.index = 0

    async def evaluate(self, *_args, **_kwargs):
        return 100

    async def eval_on_selector_all(self, *_args, **_kwargs):
        return [f"/activities/{activity_id}" for activity_id in self.pages[self.index]]

    def locator(self, selector):
        if selector == "body":
            return BodyLocator(self)
        if selector == "a[rel='next']":
            return NextLocator(self)
        return EmptyLocator()

    def get_by_role(self, *_args, **_kwargs):
        return EmptyLocator()


class PaginationTests(unittest.IsolatedAsyncioTestCase):
    def test_activity_id_order_and_total_parsing(self):
        self.assertEqual(
            _extract_activity_ids([
                "/activities/123", "/athletes/9", "/activities/456", "/activities/123"
            ]),
            ["123", "456"],
        )
        self.assertEqual(_pagination_total("1-20 of 1,205"), 1205)

    async def test_latest_n_stops_after_enough_newest_records(self):
        page = FakeTrainingPage([["6", "5"], ["4", "3"], ["2", "1"]])
        result = await discover_activity_ids(
            page, history_limit=3, scroll_rounds=0, settle_seconds=0
        )
        self.assertEqual(result, {"6", "5", "4"})
        self.assertEqual(page.index, 1)

    async def test_number_larger_than_history_downloads_everything(self):
        page = FakeTrainingPage([["5", "4"], ["3", "2"], ["1"]])
        result = await discover_activity_ids(
            page, history_limit=99, scroll_rounds=0, settle_seconds=0
        )
        self.assertEqual(result, {"1", "2", "3", "4", "5"})
        self.assertEqual(page.index, 2)

    async def test_download_all_visits_every_page(self):
        page = FakeTrainingPage([["5", "4"], ["3", "2"], ["1"]])
        result = await discover_activity_ids(
            page, history_limit="all", scroll_rounds=0, settle_seconds=0
        )
        self.assertEqual(result, {"1", "2", "3", "4", "5"})
        self.assertEqual(page.index, 2)

    async def test_routine_scan_stops_after_two_pages(self):
        page = FakeTrainingPage([["5", "4"], ["3", "2"], ["1"]])
        result = await discover_activity_ids(
            page, history_limit=None, scroll_rounds=0, settle_seconds=0
        )
        self.assertEqual(result, {"2", "3", "4", "5"})
        self.assertEqual(page.index, 1)

    async def test_incomplete_pagination_is_not_treated_as_success(self):
        page = FakeTrainingPage([["5", "4"], ["3", "2"], ["1"]], has_next=False)
        with self.assertRaisesRegex(RuntimeError, "reports 5 activities"):
            await discover_activity_ids(
                page, history_limit="all", scroll_rounds=0, settle_seconds=0
            )


if __name__ == "__main__":
    unittest.main()
