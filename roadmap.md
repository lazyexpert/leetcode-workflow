# Roadmap

Things to research and discuss later. Not committed scope.

- **LC token in `config.json` to unlock premium problems.** `fetch.py` currently hits LeetCode's public GraphQL anonymously and returns exit code 2 on premium problems (paywalled `content`). Investigate accepting an authenticated session token (`LEETCODE_SESSION` cookie or similar) via `config.json` so premium problems can be scaffolded. Open questions: secure storage (probably `.claude/` gitignored, never `config.json` itself), token refresh model, what graceful-degradation looks like when the token expires.
- **Authenticated submission to LeetCode without a browser.** Today the user solves locally and the plugin tracks timing/patterns/coverage, but the actual LC submission still happens in the browser. Investigate whether we can submit `solution.<ext>` directly via LC's API (same auth path as above) and capture the verdict (Accepted / Wrong Answer / TLE / runtime stats) into `attempts`. Would close the loop end-to-end inside Claude Code. Open questions: API stability/ToS, language→LC-language-id mapping, how to handle WA edge cases without surfacing test inputs (the pedagogical contract still applies).
