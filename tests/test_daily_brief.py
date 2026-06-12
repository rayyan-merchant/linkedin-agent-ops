from linkedin_agent_ops import daily_brief


class ReconfigurableOutput:
    def __init__(self):
        self.arguments = None

    def reconfigure(self, **kwargs):
        self.arguments = kwargs


def test_stdout_is_configured_for_unicode(monkeypatch):
    output = ReconfigurableOutput()
    monkeypatch.setattr(daily_brief.sys, "stdout", output)

    daily_brief._configure_stdout()

    assert output.arguments == {"encoding": "utf-8", "errors": "replace"}
