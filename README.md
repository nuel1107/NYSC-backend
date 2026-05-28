---
title: Tri Flow Connect API
emoji: 🛡️
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
---

# Tri-Flow Connect — FastAPI Backend

REST API for the NYSC Ikeja LGA Digital Ecosystem.

## Endpoints

| Group | Prefix | Description |
|---|---|---|
| Auth | `/auth` | Signup, signin, refresh, me |
| Profiles | `/profiles` | User profiles |
| Roles | `/roles` | Role management |
| Events | `/events` | Geofenced attendance events |
| Absence | `/absence` | Absence requests |
| Devices | `/devices` | Device binding |
| Complaints | `/complaints` | Complaint system |
| Firms | `/firms` | Corporate firms |
| Jobs | `/jobs` | Job postings |
| SAED | `/saed` | Skills, courses, clubs, rankings |
| News | `/news` | News articles |
| Community | `/community` | Community posts |
| Notifications | `/notifications` | Push notifications |
| Metrics | `/metrics` | Impact metrics |
| Uploads | `/uploads` | File presign |

Interactive docs: `https://your-space.hf.space/docs`

## Environment Variables (set in HF Spaces Secrets)

```
DATABASE_URL=postgres://...@neon.tech/triflow?sslmode=require
JWT_SECRET=your-super-secret-key
FRONTEND_URL=https://your-app.vercel.app
S3_ENDPOINT_URL=https://...r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=triflow-media
S3_PUBLIC_BASE_URL=https://pub-xxx.r2.dev
```
