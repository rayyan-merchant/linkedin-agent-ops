import re
from datetime import UTC, date, datetime

from linkedin_agent_ops.agents.performance import ContentFormat, PostMetric
from linkedin_agent_ops.models import (
    BriefItem,
    BriefSection,
    ContentOpportunity,
    DailyBrief,
    SourceKind,
)
from linkedin_agent_ops.sheets import GoogleSheetsStore


class FakeRequest:
    def __init__(self, callback):
        self.callback = callback

    def execute(self):
        return self.callback()


class FakeValues:
    def __init__(self, data):
        self.data = data

    def get(self, spreadsheetId, range):
        sheet = range.split("!", 1)[0].strip("'")
        return FakeRequest(lambda: {"values": self.data.get(sheet, [])})

    def update(self, spreadsheetId, range, valueInputOption, body):
        sheet = range.split("!", 1)[0].strip("'")

        def execute():
            self.data[sheet] = [*body["values"]]
            return {}

        return FakeRequest(execute)

    def append(
        self,
        spreadsheetId,
        range,
        valueInputOption,
        insertDataOption,
        body,
    ):
        sheet = range.split("!", 1)[0].strip("'")

        def execute():
            self.data.setdefault(sheet, []).extend(body["values"])
            return {}

        return FakeRequest(execute)

    def batchUpdate(self, spreadsheetId, body):
        def execute():
            for update in body["data"]:
                sheet, cells = update["range"].split("!", 1)
                rows = self.data[sheet.strip("'")]
                match = re.search(r"[A-Z]+(\d+)", cells)
                row_index = int(match.group(1)) - 1
                if cells.startswith("M"):
                    while len(rows[row_index]) < 13:
                        rows[row_index].append("")
                    rows[row_index][12] = update["values"][0][0]
                else:
                    rows[row_index] = update["values"][0]
            return {}

        return FakeRequest(execute)


class FakeSpreadsheets:
    def __init__(self):
        self.data = {}
        self.values_api = FakeValues(self.data)

    def values(self):
        return self.values_api

    def get(self, spreadsheetId, fields):
        return FakeRequest(
            lambda: {
                "sheets": [
                    {"properties": {"title": title}} for title in self.data
                ]
            }
        )

    def batchUpdate(self, spreadsheetId, body):
        def execute():
            for request in body["requests"]:
                title = request["addSheet"]["properties"]["title"]
                self.data.setdefault(title, [])
            return {}

        return FakeRequest(execute)


class FakeService:
    def __init__(self):
        self.api = FakeSpreadsheets()

    def spreadsheets(self):
        return self.api


def sample_brief():
    item = BriefItem(
        source_id="paper-1",
        section=BriefSection.PAPERS,
        source=SourceKind.ARXIV,
        source_name="arXiv",
        category="cs.CV",
        title="A vision paper",
        url="https://arxiv.org/abs/1",
        published_at=datetime(2026, 6, 11, tzinfo=UTC),
        summary="A sufficiently detailed factual paper summary.",
        post_angle="A practical production validation angle.",
        score=80,
    )
    return DailyBrief(
        brief_date=date(2026, 6, 12),
        generated_at=datetime(2026, 6, 12, tzinfo=UTC),
        papers=[item],
        trends=[],
        repositories=[],
        opportunity=ContentOpportunity(
            title="Connect the evidence",
            rationale="The paper has a useful production implication.",
            post_angle="Test the reported tradeoff in a real system.",
            source_urls=[item.url],
        ),
        model_used="gemini",
    )


def test_sheets_store_upserts_items_and_tracks_completion():
    service = FakeService()
    store = GoogleSheetsStore(
        spreadsheet_id="sheet-id",
        service_account_info={},
        service=service,
    )
    brief = sample_brief()

    store.record_pending("run-1", brief)
    store.record_pending("run-2", brief)

    item_rows = service.api.data["Brief Items"]
    assert len(item_rows) == 2
    assert item_rows[1][0] == "run-2"
    assert store.existing_urls(exclude_date="2026-06-12") == set()

    store.mark_delivery("run-2", "sent")
    assert store.is_completed("2026-06-12") is True


def test_sheets_store_round_trips_post_metrics():
    service = FakeService()
    store = GoogleSheetsStore(
        spreadsheet_id="sheet-id",
        service_account_info={},
        service=service,
    )
    post = PostMetric(
        post_id="post-1",
        posted_date=date(2026, 6, 12),
        format=ContentFormat.TEXT,
        topic="agents",
        pillar="technical",
        hook_type="metric",
        first_line="A technical hook.",
        impressions=100,
        reactions=5,
        comments=2,
        saves=3,
        shares=1,
        profile_clicks=1,
    )
    store.save_posts([post])
    loaded = store.load_posts()
    assert loaded[0].post_id == "post-1"
    assert loaded[0].golden_hour_comments is None
