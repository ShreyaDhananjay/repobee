"""Top-level commands for managing issues.

This module contains the top-level functions for RepoBee's issue management
functionality. Each public function in this module is to be treated as a
self-contained program.

.. module:: issues
    :synopsis: Top-level commands for issue management.

.. moduleauthor:: Simon Larsén
"""
import os
from typing import Iterable, Optional, List, Generator, Tuple, Any, Mapping

import daiquiri

import repobee_plug as plug
from colored import bg, fg, style

LOGGER = daiquiri.getLogger(__file__)


def list_issues(
    repos: Iterable[plug.Repo],
    api: plug.API,
    state: plug.IssueState = plug.IssueState.OPEN,
    title_regex: str = "",
    show_body: bool = False,
    author: Optional[str] = None,
) -> Mapping[str, List[plug.Result]]:
    """List all issues in the specified repos.

    Args:
        repos: The repos from which to fetch issues.
        api: An implementation of :py:class:`repobee_plug.API` used to
            interface with the platform (e.g. GitHub or GitLab) instance.
        state: state of the repo (open or closed). Defaults to open.
        title_regex: If specified, only issues with titles matching the regex
            are displayed. Defaults to the empty string (which matches
            everything).
        show_body: If True, the body of the issue is displayed along with the
            default info.
        author: Only show issues by this author.
    """
    # TODO optimize by not getting all repos at once
    repos = list(repos)
    repo_names = [repo.name for repo in repos]
    max_repo_name_length = max(map(len, repo_names))
    issues_per_repo = _get_issue_generator(
        repo_names=repo_names,
        state=state,
        title_regex=title_regex,
        author=author,
        api=api,
    )

    # _log_repo_issues exhausts the issues_per_repo iterator and
    # returns a list with the same information. It's important to
    # have issues_per_repo as an iterator as it greatly speeds
    # up visual feedback to the user when fetching many issues
    pers_issues_per_repo = _log_repo_issues(
        issues_per_repo, show_body, max_repo_name_length + 6
    )

    # for writing to JSON
    hook_result_mapping = {
        repo_name: [
            plug.Result(
                name="list-issues",
                status=plug.Status.SUCCESS,
                msg="Fetched {} issues from {}".format(len(issues), repo_name),
                data={issue.number: issue.to_dict() for issue in issues},
            )
        ]
        for repo_name, issues in pers_issues_per_repo
    }
    # meta hook result
    hook_result_mapping["list-issues"] = [
        plug.Result(
            name="meta",
            status=plug.Status.SUCCESS,
            msg="Meta info about the list-issues hook results",
            data={"state": state.value},
        )
    ]
    return hook_result_mapping


def _get_issue_generator(
    repo_names: List[str],
    state: plug.IssueState,
    title_regex: str,
    author: Optional[str],
    api: plug.API,
) -> Generator[
    Tuple[str, Generator[Iterable[plug.Issue], None, None]], None, None
]:
    issues_per_repo = (
        (
            repo_name,
            [
                issue
                for issue in issues
                if not author or issue.author == author
            ],
        )
        for repo_name, issues in api.get_issues(repo_names, state, title_regex)
    )
    return issues_per_repo


def _log_repo_issues(
    issues_per_repo: Tuple[str, Generator[plug.Issue, None, None]],
    show_body: bool,
    title_alignment: int,
) -> List[Tuple[Any, list]]:
    """Log repo issues.

    Args:
        issues_per_repo: (repo_name, issue generator) pairs
        show_body: Include the body of the issue in the output.
        title_alignment: Where the issue title should start counting from the
            start of the line.
    """
    even = True
    persistent_issues_per_repo = []
    for repo_name, issues in issues_per_repo:
        issues = list(issues)
        persistent_issues_per_repo.append((repo_name, issues))

        if not issues:
            LOGGER.warning("{}: No matching issues".format(repo_name))

        for issue in issues:
            color = (bg("grey_30") if even else bg("grey_15")) + fg("white")
            even = not even  # cycle color
            adjusted_alignment = title_alignment + len(
                color
            )  # color takes character space

            id_ = "{}{}/#{}:".format(color, repo_name, issue.number).ljust(
                adjusted_alignment
            )
            out = "{}{}{}{}created {!s} by {}".format(
                id_,
                issue.title,
                style.RESET,
                " ",
                issue.created_at,
                issue.author,
            )
            if show_body:
                out += os.linesep * 2 + _limit_line_length(issue.body)
            LOGGER.info(out)

    return persistent_issues_per_repo


def _limit_line_length(s: str, max_line_length: int = 100) -> str:
    """Return the input string with lines no longer than max_line_length.

    Args:
        s: Any string.
        max_line_length: Maximum allowed line length.
    Returns:
        the input string with lines no longer than max_line_length.
    """
    lines = s.split(os.linesep)
    out = ""
    for line in lines:
        cur = 0
        while len(line) - cur > max_line_length:
            # find ws closest to the line length
            idx = line.rfind(" ", cur, max_line_length + cur)
            idx = max_line_length + cur if idx <= 0 else idx
            if line[idx] == " ":
                out += line[cur:idx]
            else:
                out += line[cur : idx + 1]
            out += os.linesep
            cur = idx + 1
        out += line[cur : cur + max_line_length] + os.linesep
    return out


def open_issue(
    issue: plug.Issue,
    master_repo_names: Iterable[str],
    teams: Iterable[plug.Team],
    api: plug.API,
) -> None:
    """Open an issue in student repos.

    Args:
        master_repo_names: Names of master repositories.
        teams: Team objects specifying student groups.
        issue: An issue to open.
        api: An implementation of :py:class:`repobee_plug.API` used to
            interface with the platform (e.g. GitHub or GitLab) instance.
    """
    repo_names = plug.generate_repo_names(teams, master_repo_names)
    api.open_issue(issue.title, issue.body, repo_names)


def close_issue(
    title_regex: str, repos: Iterable[plug.Repo], api: plug.API
) -> None:
    """Close issues whose titles match the title_regex in student repos.

    Args:
        title_regex: A regex to match against issue titles.
        master_repo_names: Names of master repositories.
        teams: Team objects specifying student groups.
        api: An implementation of :py:class:`repobee_plug.API` used to
            interface with the platform (e.g. GitHub or GitLab) instance.
    """
    repo_names = (repo.name for repo in repos)
    api.close_issue(title_regex, repo_names)
