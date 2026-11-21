# Documentary Hybrid 2.5D (isolated branch)

This branch is an isolated implementation track for a 2–3 minute Indonesian visual-documentary pipeline. It does not change the repository's `main` branch and does not reconnect to TeknoSaku.

## Locked output profile

- Rendering approach: hybrid 2.5D (one Blender still per scene, animated 2D infographic/camera layers, FFmpeg final assembly)
- Delivery: 1080 × 1920, 30 fps, H.264 + AAC
- Runtime: 120–180 seconds
- Visual direction: dark navy investigative / isometric blueprint palette with orange highlights
- Review policy: render-only; no automatic YouTube upload

## What is implemented on this branch

1. Documentary script constraints: 10–12 scenes and 300–390 Indonesian words, with verified-fact references.
2. Runtime guard: refuses to render if the generated timeline is outside 120–180 seconds.
3. Blueprint palette and orthographic isometric camera mode in Blender.
4. Reusable 3D investigative props: money, gold bars, house, courthouse, documents, and car, alongside the original reusable prop set.
5. Offline end-to-end smoke test using synthetic narration audio; no API key or external service required.
6. GitHub Actions CI for unit tests and the offline render test.
7. A manual phone-triggered render workflow that always uses `--dry-run`, so it creates a review artifact and never uploads automatically.

## Run from an iPhone browser

1. Open the repository and select branch `documentary-hybrid-2-5d`.
2. Open **Actions**.
3. Select **documentary-render**.
4. Tap **Run workflow**, choose `fast`, and start the run.
5. Open the completed run and download the `documentary-review` artifact.
6. Review `video.mp4`, `script.json`, and `facts.json` before any manual publishing decision.

## Free-tier requirements and limits

- Add `GEMINI_API_KEY` as a repository Actions secret from Google AI Studio. The configured model fallback list is limited to models whose official pricing page currently lists a free tier. Keep the Google project on the free tier and do not enable paid billing; requests can still stop when free quotas are reached. Free-tier availability and quotas can change.
- Edge TTS is used for narration and does not require a paid API subscription, but it does require network access during the job.
- GitHub Actions standard hosted runners are free for public repositories. Artifacts and caches still have storage limits, and jobs have runtime limits. This design uses standard Ubuntu runners only; it does not use billable larger runners. This does not remove platform throttling or availability limits.
- No Cloudflare, paid video-generation API, paid TTS API, YouTube OAuth, or YouTube upload permission is required for the review render.
- The first full render can fail if a free API quota is exhausted, a feed is unavailable, or a runner hits its time limit. Such a run must be reported as failed, not displayed as active work.

## Current validation status

The source changes and test workflows have been committed to this branch. A green GitHub Actions run and a successfully downloaded, inspected review video are still required before calling the implementation production-ready. The connector used for this work can write repository files but does not expose a direct workflow-dispatch or run-status action, so that final execution result must be checked in the GitHub Actions page.

## Editorial and rights safeguards

- The facts engine checks script claims against source evidence; it cannot independently guarantee that a source itself is correct.
- Keep source URLs and publisher attribution with the output.
- Do not reuse third-party news footage or photographs unless the usage rights permit it. Prefer original procedural 3D scenes, licensed assets, or clearly attributed material with permission.
- Allegations must remain attributed and must not be presented as proven facts unless the cited source establishes that status.
