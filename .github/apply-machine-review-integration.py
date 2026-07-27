from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    source = target.read_text(encoding='utf-8')
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected exactly one anchor, found {count}')
    target.write_text(source.replace(old, new), encoding='utf-8')


replace_once(
    'website/components/Sidebar.tsx',
    "  source_identity?: string;\n  legacy_ids?: string[];",
    "  source_identity?: string;\n  machine_translation?: boolean;\n  human_verified?: boolean;\n  legacy_ids?: string[];",
)

replace_once(
    'website/app/api/admin/submissions/[id]/route.ts',
    "import {\n  createProofreadingPullRequest,\n  ProofreadingPullRequestError,\n  readProofreadingPullRequestState,\n} from '@/lib/github-proofreading';\n",
    "import {\n  createProofreadingPullRequest,\n  ProofreadingPullRequestError,\n  readProofreadingPullRequestState,\n} from '@/lib/github-proofreading';\nimport {\n  MACHINE_TRANSLATION_ID_SET,\n  setMachineTranslationReviewState,\n} from '@/lib/machine-translation-review';\n",
)

replace_once(
    'website/app/api/admin/submissions/[id]/route.ts',
    "      const completed = await transitionOrConflict(\n        context.kv,\n        processing,\n        'pr_created',\n        {\n          review,\n          pull_request: pullRequest,\n          processing_error: '',\n        },\n      );\n      return NextResponse.json(\n",
    "      const completed = await transitionOrConflict(\n        context.kv,\n        processing,\n        'pr_created',\n        {\n          review,\n          pull_request: pullRequest,\n          processing_error: '',\n        },\n      );\n      if (MACHINE_TRANSLATION_ID_SET.has(completed.story_id)) {\n        await setMachineTranslationReviewState(\n          context.kv,\n          completed.story_id,\n          {\n            verified: true,\n            reviewer: context.authentication.identity.label,\n            reviewed_at: review.reviewed_at,\n            note: review.public_message || '社区校对投稿已批准并建立 PR',\n            submission_id: completed.id,\n            pull_request_url: pullRequest.url,\n          },\n        );\n      }\n      return NextResponse.json(\n",
)

replace_once(
    '.github/workflows/deploy-exedra-proofreading-test.yml',
    '          fetch-depth: 1\n',
    '          fetch-depth: 0\n',
)
replace_once(
    '.github/workflows/deploy-exedra-proofreading-test.yml',
    "      - name: Generate complete deployable story data\n        run: python generate_story_index.py\n\n      - name: Install website dependencies\n",
    "      - name: Generate complete deployable story data\n        run: |\n          python generate_story_index.py\n          python generate_machine_translation_manifest.py \\\n            --translation-commit 3d463befe7a10d4cb72034378ce2a6f23c377abb \\\n            --check\n\n      - name: Install website dependencies\n",
)
replace_once(
    '.github/workflows/deploy-exedra-proofreading-test.yml',
    "          curl --fail --silent --show-error \"$SITE_URL/api/proofreading/config\" -o \"$RUNNER_TEMP/config.json\"\n          python - \"$RUNNER_TEMP/home.html\" \"$RUNNER_TEMP/story-index.json\" \"$RUNNER_TEMP/config.json\" <<'PY'\n",
    "          curl --fail --silent --show-error \"$SITE_URL/api/proofreading/config\" -o \"$RUNNER_TEMP/config.json\"\n          curl --fail --silent --show-error \"$SITE_URL/api/proofreading/machine-status\" -o \"$RUNNER_TEMP/machine-status.json\"\n          python - \"$RUNNER_TEMP/home.html\" \"$RUNNER_TEMP/story-index.json\" \"$RUNNER_TEMP/config.json\" \"$RUNNER_TEMP/machine-status.json\" <<'PY'\n",
)
replace_once(
    '.github/workflows/deploy-exedra-proofreading-test.yml',
    "          config = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))\n",
    "          config = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))\n          machine = json.loads(Path(sys.argv[4]).read_text(encoding='utf-8'))\n",
)
replace_once(
    '.github/workflows/deploy-exedra-proofreading-test.yml',
    "          if config.get('target_branch') != 'EXEDRA-TEST':\n              raise SystemExit(f'Unexpected target branch: {config}')\n          print(f\"SITE_OK stories={len(stories)} turnstile_test_mode={config.get('turnstile_test_mode')}\")\n",
    "          if config.get('target_branch') != 'EXEDRA-TEST':\n              raise SystemExit(f'Unexpected target branch: {config}')\n          if machine.get('total', 0) <= 0 or machine.get('remaining') != machine.get('total') - machine.get('verified', 0):\n              raise SystemExit(f'Invalid machine translation status: {machine}')\n          print(f\"SITE_OK stories={len(stories)} machine_total={machine['total']} machine_remaining={machine['remaining']} turnstile_test_mode={config.get('turnstile_test_mode')}\")\n",
)

replace_once(
    '.github/workflows/community-proofreading-pr.yml',
    "      - name: Generate and validate complete story catalogue\n        run: python generate_story_index.py\n\n      - name: Install website dependencies\n",
    "      - name: Generate and validate complete story catalogue\n        run: |\n          python generate_story_index.py\n          python generate_machine_translation_manifest.py \\\n            --translation-commit 3d463befe7a10d4cb72034378ce2a6f23c377abb \\\n            --check\n\n      - name: Install website dependencies\n",
)

replace_once(
    'website/app/review/machine-translations/page.tsx',
    "magi-proofreading-admin-token",
    "magi-reader-proofreading-admin-token",
)
