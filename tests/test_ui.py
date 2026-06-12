def test_ui_imports_without_starting_streamlit():
    from linkedin_agent_ops import ui

    assert callable(ui.main)

