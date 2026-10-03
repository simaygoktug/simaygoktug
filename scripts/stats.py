"""Render an all-time GitHub stats card (SVG) for the profile README.

Usage: python scripts/stats.py assets/stats.svg
Token: STATS_TOKEN (a PAT, counts private work too) or GITHUB_TOKEN.
"""
import json
import os
import sys
import urllib.request
from html import escape

LOGIN = "simaygoktug"
API = "https://api.github.com/graphql"


def gql(query, variables, token):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": LOGIN},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


PROFILE_Q = """
query($login: String!, $prs: String!, $reviews: String!) {
  prs: search(query: $prs, type: ISSUE) { issueCount }
  reviews: search(query: $reviews, type: ISSUE) { issueCount }
  user(login: $login) {
    followers { totalCount }
    contributionsCollection { contributionYears }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

YEAR_Q = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      contributionCalendar { totalContributions }
    }
  }
}
"""


def collect(token):
    # Search covers private org repos the token can see; contributionsCollection does not.
    data = gql(PROFILE_Q, {"login": LOGIN,
                           "prs": f"is:pr author:{LOGIN}",
                           "reviews": f"is:pr reviewed-by:{LOGIN} -author:{LOGIN}"}, token)
    user = data["user"]
    totals = dict(commits=0, issues=0, contributions=0,
                  prs=data["prs"]["issueCount"], reviews=data["reviews"]["issueCount"])
    for year in user["contributionsCollection"]["contributionYears"]:
        c = gql(YEAR_Q, {"login": LOGIN, "from": f"{year}-01-01T00:00:00Z",
                         "to": f"{year}-12-31T23:59:59Z"}, token)["user"]["contributionsCollection"]
        totals["commits"] += c["totalCommitContributions"]
        totals["issues"] += c["totalIssueContributions"]
        totals["contributions"] += c["contributionCalendar"]["totalContributions"]

    repos = user["repositories"]["nodes"]
    langs = {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            size, color = langs.get(name, (0, e["node"]["color"] or "#8b949e"))
            langs[name] = (size + e["size"], color)
    top = sorted(langs.items(), key=lambda kv: kv[1][0], reverse=True)[:6]
    total_bytes = sum(v[0] for _, v in top) or 1

    totals["repos"] = user["repositories"]["totalCount"]
    totals["stars"] = sum(r["stargazerCount"] for r in repos)
    totals["followers"] = user["followers"]["totalCount"]
    totals["languages"] = [(n, s / total_bytes, c) for n, (s, c) in top]
    return totals


def render(t):
    w, h = 720, 250
    cells = [
        ("Contributions", t["contributions"]),
        ("Commits", t["commits"]),
        ("Pull requests", t["prs"]),
        ("PR reviews", t["reviews"]),
        ("Repositories", t["repos"]),
        ("Issues", t["issues"]),
    ]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           'role="img" aria-label="GitHub stats, all time">',
           "<style>",
           ":root{--bg:#ffffff;--border:#d0d7de;--fg:#1f2328;--muted:#59636e;--accent:#0969da}",
           "@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--border:#30363d;--fg:#e6edf3;--muted:#9198a1;--accent:#4493f8}}",
           "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}",
           ".t{fill:var(--fg);font-size:18px;font-weight:600}",
           ".n{fill:var(--fg);font-size:24px;font-weight:600}",
           ".l{fill:var(--muted);font-size:12px}",
           ".g{fill:var(--fg);font-size:12px}",
           "</style>",
           f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="var(--bg)" stroke="var(--border)"/>',
           '<text x="24" y="38" class="t">GitHub stats · all time</text>']

    col_w = (w - 48) / len(cells)
    for i, (label, value) in enumerate(cells):
        x = 24 + i * col_w
        out.append(f'<text x="{x:.0f}" y="88" class="n">{value:,}</text>')
        out.append(f'<text x="{x:.0f}" y="108" class="l">{escape(label)}</text>')

    out.append('<text x="24" y="150" class="l">Most used languages</text>')
    bar_x, bar_w = 24, w - 48
    out.append(f'<clipPath id="bar"><rect x="{bar_x}" y="162" width="{bar_w}" height="10" rx="5"/></clipPath>')
    out.append('<g clip-path="url(#bar)">')
    x = bar_x
    for name, share, color in t["languages"]:
        seg = share * bar_w
        out.append(f'<rect x="{x:.2f}" y="162" width="{seg:.2f}" height="10" fill="{color}"/>')
        x += seg
    out.append("</g>")

    for i, (name, share, color) in enumerate(t["languages"]):
        lx = 24 + (i % 3) * 224
        ly = 200 + (i // 3) * 26
        out.append(f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>')
        out.append(f'<text x="{lx + 16}" y="{ly}" class="g">{escape(name)} '
                   f'<tspan class="l">{share * 100:.1f}%</tspan></text>')

    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    token = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Set STATS_TOKEN or GITHUB_TOKEN")
    path = sys.argv[1] if len(sys.argv) > 1 else "assets/stats.svg"
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(collect(token)))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
