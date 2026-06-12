from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import streamlit as st

from linkedin_agent_ops.agents.performance import parse_posts_csv


def api_url() -> str:
    return os.getenv("AGENT_API_URL", "http://127.0.0.1:8000").rstrip("/")


def request_json(method: str, path: str, **kwargs):
    try:
        response = httpx.request(
            method,
            f"{api_url()}{path}",
            timeout=180,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text
        st.error(detail)
    except httpx.HTTPError as exc:
        st.error(f"API unavailable: {exc}")
    return None


def show_result(result: dict, *, marp: str | None = None) -> None:
    validation = result.get("metadata", {}).get("validation", {})
    if validation.get("passed"):
        st.success("Validation passed")
    else:
        st.warning("Output has unresolved validation issues")
    for issue in validation.get("issues", []):
        st.write(f"**{issue['severity']} - {issue['code']}:** {issue['message']}")
    st.json(result.get("result", result))
    st.download_button(
        "Download JSON",
        json.dumps(result, indent=2),
        file_name=f"{result.get('metadata', {}).get('agent', 'agent')}.json",
        mime="application/json",
    )
    st.download_button(
        "Download Markdown",
        "```json\n" + json.dumps(result.get("result", result), indent=2) + "\n```\n",
        file_name=f"{result.get('metadata', {}).get('agent', 'agent')}.md",
        mime="text/markdown",
    )
    if marp:
        st.download_button(
            "Download Marp Markdown",
            marp,
            file_name="carousel.md",
            mime="text/markdown",
        )


def post_architecture_page() -> None:
    st.header("Post Architecture")
    with st.form("post-architecture"):
        topic = st.text_input("Topic")
        insight = st.text_area("Key insight")
        evidence = st.text_area("Metric or evidence (optional)")
        preferred = st.selectbox(
            "Preferred format", ["any", "text", "carousel", "image", "video"]
        )
        audience = st.text_input("Audience override (optional)")
        submitted = st.form_submit_button("Generate architecture")
    if submitted:
        result = request_json(
            "POST",
            "/agents/post-architecture",
            json={
                "topic": topic,
                "key_insight": insight,
                "metric_or_evidence": evidence or None,
                "preferred_format": preferred,
                "audience_override": audience or None,
            },
        )
        if result:
            show_result(result)


def paper_page() -> None:
    st.header("Paper-to-Post Brief")
    mode = st.radio("Input", ["arXiv URL", "PDF upload"])
    url = st.text_input("arXiv URL") if mode == "arXiv URL" else ""
    upload = st.file_uploader("PDF", type=["pdf"]) if mode == "PDF upload" else None
    if st.button("Analyze paper"):
        files = None
        data = {"arxiv_url": url or ""}
        if upload:
            files = {"file": (upload.name, upload.getvalue(), "application/pdf")}
        result = request_json(
            "POST",
            "/agents/paper",
            data=data,
            files=files,
        )
        if result:
            show_result(result)


def carousel_page() -> None:
    st.header("Carousel Architect")
    with st.form("carousel"):
        topic = st.text_input("Topic")
        points = st.text_area("Key points, one per line")
        audience = st.text_input("Audience (optional)")
        source = st.text_area("Source brief (optional)")
        count = st.slider("Slides", 8, 10, 10)
        submitted = st.form_submit_button("Design carousel")
    if submitted:
        result = request_json(
            "POST",
            "/agents/carousel",
            json={
                "topic": topic,
                "key_points": [line.strip() for line in points.splitlines() if line.strip()],
                "audience": audience or None,
                "source_brief": source or None,
                "slide_count": count,
            },
        )
        if result:
            show_result(result, marp=result.pop("marp_markdown", None))


def performance_page() -> None:
    st.header("Performance Analyzer")
    upload = st.file_uploader("Post metrics CSV", type=["csv"])
    goal = st.text_input(
        "Analysis goal",
        "Improve useful reach, saves, and technical discussion.",
    )
    save_to_sheets = st.checkbox("Save imported posts to Google Sheets")
    if st.button("Analyze performance") and upload:
        try:
            posts = [
                post.model_dump(mode="json")
                for post in parse_posts_csv(upload.getvalue())
            ]
        except ValueError as exc:
            st.error(str(exc))
            return
        result = request_json(
            "POST",
            "/agents/performance",
            json={"posts": posts, "analysis_goal": goal},
        )
        if result:
            show_result(result)
        if save_to_sheets:
            request_json(
                "POST",
                "/analytics/import",
                files={"file": (upload.name, upload.getvalue(), "text/csv")},
            )


def cricket_page() -> None:
    st.header("Cricket CV Build Log")
    with st.form("cricket"):
        week = st.number_input("Week", min_value=1, value=1)
        completed = st.text_area("Work completed")
        failures = st.text_area("Failures")
        current = st.text_area(
            "Current metrics JSON",
            '[{"name":"ball detection mAP","value":0.73,"unit":"mAP","better_when":"higher"}]',
        )
        previous = st.text_area("Previous metrics JSON", "[]")
        visuals = st.text_area("Available visual assets, one per line")
        submitted = st.form_submit_button("Generate build-log brief")
    if submitted:
        try:
            payload = {
                "week_number": int(week),
                "work_completed": completed,
                "failures": failures,
                "current_metrics": json.loads(current),
                "previous_metrics": json.loads(previous),
                "available_visual_assets": [
                    line.strip() for line in visuals.splitlines() if line.strip()
                ],
            }
        except json.JSONDecodeError as exc:
            st.error(f"Invalid metrics JSON: {exc}")
            return
        result = request_json("POST", "/agents/cricket-build-log", json=payload)
        if result:
            show_result(result)


def history_page() -> None:
    st.header("Agent History")
    result = request_json("GET", "/history")
    if result is not None:
        st.dataframe(result, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="LinkedIn Agent Ops", layout="wide")
    st.title("LinkedIn Agent Ops")
    pages = {
        "Post Architecture": post_architecture_page,
        "Paper Brief": paper_page,
        "Carousel": carousel_page,
        "Performance": performance_page,
        "Cricket Build Log": cricket_page,
        "History": history_page,
    }
    selection = st.sidebar.radio("Agent", list(pages))
    pages[selection]()


def run() -> None:
    raise SystemExit(
        subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(Path(__file__).resolve()),
            ],
            check=False,
        ).returncode
    )


if __name__ == "__main__":
    main()
