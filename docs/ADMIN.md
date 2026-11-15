# Admin dashboard

Open **https://www.mhraaga.in/admin.html** (also the **Admin** entry at the bottom of the sidebar, shown only to administrators).
Sign in with an administrator account. `keshav.velhal@gmail.com` is the **owner**.

## Who is an administrator
| Type | How | What it can do |
|---|---|---|
| **Owner** | The emails in the `ADMIN_EMAILS` setting of the stack (currently `keshav.velhal@gmail.com`). Not editable from the dashboard. | Everything, including making and removing administrators and deleting anyone except owners. Can never be demoted, disabled or deleted. |
| **Admin** | A user whose type is set to *Admin* by an owner. | See every tab, edit names, limits, status, custom values and passwords of normal users, add and delete normal users, edit the AI rules. Cannot change types, and cannot touch other administrators' status. |
| **User** | Everyone else. | The normal site. |

Every admin call is checked again on the server; hiding the page from users is only a convenience.

## Tabs
**Overview**: users, admins, disabled accounts, songs made, songs today, AI-voice spend today against its caps, the number and size of cached voice files, new users per day (14 days), voice spend per day (14 days) and the **recent admin actions** (an audit log of who changed what, kept 180 days; passwords are never logged).

**Users**: a searchable table with a type filter. Columns: name, email, type, status, songs, today's count against the limit, voice spend today, joined, last sign-in, and every **custom column**. *Edit* opens a form to change:
- the **name** (the username shown to others),
- the **type** (User or Admin; owners only),
- **songs per day** for this person (empty means the site default of 30),
- **disabled** (they cannot sign in and their sessions stop working),
- a **new password** (sets it immediately; also clears a lockout),
- every custom column,
- plus **Reset today's quota** and **Delete user** (removes the user and all their songs; you must type their email to confirm).
*+ Add user* creates an account with a name, email, password and type.

**Columns**: add your own fields to every user record, for example *plan* (select: free or pro), *city* (text), *seats* (number), *paid* (yes/no), *paid until* (date). A key is lowercase letters, digits and `_` (up to 24 characters), 20 columns at most. The values are stored on the user record in DynamoDB (`extra`). Removing a column hides it; the stored values stay.

**Cloud cost**: the AWS bill from Cost Explorer (this month so far, last month, a projection, the last 30 days per day and this month by service, with the services mhRaaga uses marked), OpenRouter usage from the key's own counters, and the AI voice spend counted by the site. The report is cached for an hour; *Refresh* runs a new query (AWS charges about one cent per query, so refresh is limited to once every five minutes).

## Things to know
- **The AWS figures are for the whole AWS account**, not just mhRaaga. If the account also runs other projects, their cost is in the total. The "services mhRaaga uses" line adds up Lambda, DynamoDB, S3, CloudFront, API Gateway, Route 53, Systems Manager, CloudWatch, Certificate Manager and KMS, which is an upper bound for this project because other projects may use the same services.
- AWS posts costs several hours late, so "today" is incomplete.
- OpenRouter shows what the key has used; if it has no spending limit set, there is no cap there. The site's own caps (per user per day, per site per day) are in [VOICE.md](VOICE.md).
- Custom columns are data you keep about people. Keep to what you need, and follow the privacy rules that apply to you.

## API
All under `/api/admin`, administrators only:
`GET /users` · `POST /users` · `PATCH /users/{email}` · `POST /users/{email}/delete` · `GET /schema` · `PUT /schema` · `GET /stats` · `GET /costs[?refresh=1]`. Details and checks are in `api/admin.py`; tests are in `tests/test_admin.py`.
Also: `PATCH /api/me {name}` lets any user change their own display name.
