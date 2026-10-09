# Search syntax

The same language works in the GUI (Explorer, Search, global search, smart collections) and the CLI
(`arcivo search …`, `arcivo export …`). Clauses are combined with **AND**; use `OR` between neighbouring clauses
and `-` to negate. Quote values containing spaces.

| Clause | Example | Meaning |
|---|---|---|
| words | `invoice march` | full-text (text, captions, file names, senders, sources, audio tags); prefix-matching, accent-insensitive |
| `"phrase"` | `"meeting notes"` | exact phrase |
| `type:` | `type:audio,voice` | `text photo image video video_note gif audio voice document file media link sticker contact location poll dice …` |
| `ext:` / `mime:` | `ext:pdf,docx` · `mime:image/*` | file extension / MIME type |
| `filename:` / `caption:` | `filename:report` | match only in that field |
| `sender:` / `from:` | `sender:@alice` · `sender:"Sara Ahmadi"` · `sender:me` | original sender |
| `chat:` / `channel:` / `in:` | `chat:"Dev Notes"` | source chat of a forwarded message |
| `domain:` | `domain:github.com` | messages containing links to a domain |
| `after:` / `before:` / `date:` | `after:2026-01-01` · `before:2026-02` · `date:2025` · `date:2025-01..2025-06` · `date:last7d` | date filters (after is inclusive); also `today`, `yesterday` |
| `size:` | `size:>50MB` · `size:<1GB` · `size:10MB..100MB` | file size (B, KB, MB, GB) |
| `duration:` | `duration:>5m` · `duration:1:30..10:00` | media duration (s, m, h or mm:ss) |
| `tag:` | `tag:work,music` · `-tag:archive` | local tags |
| `has:` | `has:link` · `has:media` · `has:caption` · `has:tag` · `has:note` | presence |
| `is:` | `is:flagged` · `is:starred` · `is:forwarded` · `is:album` · `is:edited` · `is:deleted` | state |
| `sort:` / `order:` | `sort:size` · `sort:date-asc` · `sort:duration` · `order:asc` | ordering |

## Examples

```text
type:audio size:>20MB sort:size                 large music files, biggest first
ext:pdf after:2026-01-01 -tag:read              this year's PDFs not tagged "read"
type:video duration:>10m                        long videos
(type:photo OR type:video) date:2025            photos and videos saved in 2025
domain:youtube.com is:forwarded                 forwarded YouTube links
sender:"Mina Rahimi" has:media                  media from one person
```

Invalid queries are reported with the position of the problem (`search_syntax` error) instead of silently
returning nothing.
