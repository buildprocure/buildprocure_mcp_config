from tools.pr_review_tools import PRReviewTool


def test_pr_review_tool_metadata():
    tool = PRReviewTool()
    tools = tool.get_tools()
    names = [t["name"] for t in tools]

    assert "list_open_pull_requests" in names
    assert "get_pull_request_details" in names
    assert "get_pr_review_context" in names