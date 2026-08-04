[CmdletBinding()]
param(
    [string]$Repo = 'D:\magia\MyProducts\magi-reader-exedra-test',
    [string]$ScenarioRoot = 'D:\magia\Madoka Magica Magia Exedra TW\Resources\Scenarios',
    [string]$ManifestRoot = 'D:\magia\Madoka Magica Magia Exedra TW\Resources\Manifests'
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$Target = 'EXEDRA-TEST'
$Remote = 'origin'
$GitHubRepo = 'HiiragiNemu/magi-reader'
$Workflow = 'deploy-exedra-proofreading-test.yml'
$Site = 'https://magireader-exedra-cn-test.crynetsystemscell.workers.dev'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令失败：$Command $($Arguments -join ' ')"
    }
}

function Resolve-ManifestRoot {
    param([string]$Requested)
    $required = @(
        'getFieldStageMstList.json',
        'getAdvMstList.json',
        'getCollectionConditionMstList.json'
    )
    $candidates = @(
        $Requested,
        (Join-Path (Split-Path -Parent $ScenarioRoot) 'Manifests'),
        'D:\magia\Madoka Magica Magia Exedra TW\Resources\Manifests'
    ) | Where-Object { $_ } | Select-Object -Unique
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { continue }
        $ok = $true
        foreach ($name in $required) {
            if (-not (Test-Path -LiteralPath (Join-Path $candidate $name) -PathType Leaf)) {
                $ok = $false
                break
            }
        }
        if ($ok) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    $searchRoot = 'D:\magia\Madoka Magica Magia Exedra TW'
    if (Test-Path -LiteralPath $searchRoot) {
        $match = Get-ChildItem -LiteralPath $searchRoot -Recurse -Filter 'getAdvMstList.json' -File -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($match) {
            $candidate = $match.Directory.FullName
            foreach ($name in $required) {
                if (-not (Test-Path -LiteralPath (Join-Path $candidate $name) -PathType Leaf)) {
                    throw "找到 getAdvMstList，但同目录缺少 $name：$candidate"
                }
            }
            return $candidate
        }
    }
    throw '找不到包含 getFieldStageMstList/getAdvMstList/getCollectionConditionMstList 的 Manifests 目录。'
}

if (-not (Test-Path -LiteralPath (Join-Path $Repo '.git'))) {
    throw "不是 Git 仓库：$Repo"
}
if (-not (Test-Path -LiteralPath $ScenarioRoot -PathType Container)) {
    throw "台服简体 Scenario 目录不存在：$ScenarioRoot"
}
$ScenarioRoot = (Resolve-Path -LiteralPath $ScenarioRoot).Path
$ManifestRoot = Resolve-ManifestRoot -Requested $ManifestRoot

$ScenarioFiles = @(Get-ChildItem -LiteralPath $ScenarioRoot -Recurse -Filter '*.json' -File)
if ($ScenarioFiles.Count -ne 2780) {
    throw "台服 Scenario JSON 数量异常：$($ScenarioFiles.Count)，预期 2780。"
}
Write-Host "台服 Scenario：$ScenarioRoot"
Write-Host "Scenario JSON：$($ScenarioFiles.Count)"
Write-Host "官方命名 Manifests：$ManifestRoot"

Set-Location $Repo
Invoke-Native git -C $Repo remote set-url $Remote 'https://github.com/HiiragiNemu/magi-reader.git'
Invoke-Native git -C $Repo fetch $Remote --prune

$OldWorkerSha = (& git -C $Repo rev-parse "refs/remotes/$Remote/$Target").Trim()
if ($LASTEXITCODE -ne 0 -or -not $OldWorkerSha) {
    throw "无法读取 $Remote/$Target"
}
$MainBefore = (& git -C $Repo rev-parse "refs/remotes/$Remote/main").Trim()
Write-Host "远端 EXEDRA-TEST 覆盖前提交：$OldWorkerSha"
Write-Host "main 保持：$MainBefore"

$ImplementationPaths = @(
    'tools/tw_official_import_core.py',
    'tools/materialize_tw_official_cn.py',
    'tools/apply_tw_official_features.py',
    'tools/build_split_search_indexes.py',
    'tools/patch_tw_deploy_workflow.py',
    'tools/validate_tw_official_coverage.py',
    'tools/sync_tw_official_to_exedra_test.ps1'
)
Invoke-Native git -C $Repo checkout "$Remote/$Target" -- @ImplementationPaths

# 保存当前本地进度，但绝不推送 main。
Invoke-Native git -C $Repo add --all
& git -C $Repo diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    Invoke-Native git -C $Repo commit -m "Checkpoint local progress before TW official import $Stamp"
} elseif ($LASTEXITCODE -ne 0) {
    throw '无法检查导入前暂存区。'
}

Write-Host ''
Write-Host '[1/6] 注入台服官方简体剧情并生成 JSON/TXT、官方命名和 UI……'
Invoke-Native python tools/materialize_tw_official_cn.py `
    --scenario-root $ScenarioRoot `
    --manifest-root $ManifestRoot

$ReportPath = Join-Path $Repo 'artifacts\exedra_official_tw_import_report.json'
$MetadataPath = Join-Path $Repo 'artifacts\tw_official_metadata.generated.json'
if (-not (Test-Path -LiteralPath $ReportPath)) { throw "缺少导入报告：$ReportPath" }
if (-not (Test-Path -LiteralPath $MetadataPath)) { throw "缺少官方元数据：$MetadataPath" }
$Report = Get-Content -LiteralPath $ReportPath -Raw -Encoding utf8 | ConvertFrom-Json
$Stats = $Report.stats
if (-not $Stats) { throw '台服导入报告缺少 stats。' }
if ([int]$Stats.official_tw_groups -le 0) { throw '没有生成任何台服官方剧情组。' }
if ([int]$Stats.failed_groups -ne 0) { throw "存在结构失败：$($Stats.failed_groups)" }
if ([int]$Stats.tw_source_files -ne 2780) { throw "来源文件统计异常：$($Stats.tw_source_files)" }
if ([int]$Stats.tw_source_files_used -ne 2780 -or [int]$Stats.tw_source_files_unused -ne 0) {
    throw "并非全部 2780 个台服 Scenario 均已注入：used=$($Stats.tw_source_files_used), unused=$($Stats.tw_source_files_unused)"
}
Write-Host ("台服注入通过：groups={0}, json={1}, events={2}, used={3}/2780" -f `
    $Stats.official_tw_groups, $Stats.official_tw_json_files, `
    $Stats.official_tw_text_events, $Stats.tw_source_files_used)

Write-Host ''
Write-Host '[2/6] 验证章节名、小节名和台服标记……'
$StoryIndexPath = Join-Path $Repo 'website\public\story_index.json'
$Stories = @(Get-Content -LiteralPath $StoryIndexPath -Raw -Encoding utf8 | ConvertFrom-Json)
$OfficialStories = @($Stories | Where-Object { $_.official_tw -eq $true })
if ($OfficialStories.Count -ne [int]$Stats.official_tw_groups) {
    throw "story_index 台服标记数量不一致：$($OfficialStories.Count) != $($Stats.official_tw_groups)"
}
if (-not ($OfficialStories | Where-Object { $_.official_tw_chapter_title } | Select-Object -First 1)) {
    throw '未应用 getFieldStageMstList 章节名。'
}
if (-not ($OfficialStories | Where-Object { @($_.official_tw_section_titles).Count -gt 0 } | Select-Object -First 1)) {
    throw '未应用 getAdvMstList 小节名。'
}

Write-Host ''
Write-Host '[3/6] 完整检查、Worker 构建和拆分搜索验证……'
Push-Location (Join-Path $Repo 'website')
try {
    Invoke-Native npm.cmd ci
    Invoke-Native npm.cmd run check
    Invoke-Native npm.cmd run build:worker
    Invoke-Native npm.cmd run verify:cloudflare-output
} finally {
    Pop-Location
}
Invoke-Native python tools/build_split_search_indexes.py --validate-only

foreach ($scope in @('magireco', 'exedra')) {
    $manifest = Join-Path $Repo "website\public\search_index_manifest.$scope.json"
    $payload = Join-Path $Repo "artifacts\search-split\search_content.$scope.json"
    if (-not (Test-Path -LiteralPath $manifest)) { throw "缺少拆分搜索 manifest：$scope" }
    if (-not (Test-Path -LiteralPath $payload)) { throw "缺少拆分搜索对象：$scope" }
}

Write-Host ''
Write-Host '[4/6] 提交最终生成内容……'
Invoke-Native git -C $Repo add --all
& git -C $Repo diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    # 该前缀会让云端紧凑包物化工作流跳过本次已经认证的本地生成提交。
    Invoke-Native git -C $Repo commit -m "[tw-materialized] Official TW zh-CN data, UI and split search $Stamp"
} elseif ($LASTEXITCODE -ne 0) {
    throw '无法检查最终暂存区。'
} else {
    throw '生成后没有任何可提交变化，拒绝覆盖远端。'
}
$NewWorkerSha = (& git -C $Repo rev-parse HEAD).Trim()

Invoke-Native git -C $Repo fetch $Remote --prune
$CurrentRemoteSha = (& git -C $Repo rev-parse "refs/remotes/$Remote/$Target").Trim()
if ($CurrentRemoteSha -ne $OldWorkerSha) {
    throw "执行期间 EXEDRA-TEST 被更新：$OldWorkerSha -> $CurrentRemoteSha"
}

Write-Host ''
Write-Host '[5/6] 覆盖 EXEDRA-TEST，main 不变……'
Invoke-Native git -C $Repo push $Remote `
    "HEAD:refs/heads/$Target" `
    "--force-with-lease=refs/heads/${Target}:${OldWorkerSha}"
$RemoteAfter = ((& git -C $Repo ls-remote $Remote "refs/heads/$Target") -split "`t")[0].Trim()
if ($RemoteAfter -ne $NewWorkerSha) { throw "远端核对失败：$RemoteAfter != $NewWorkerSha" }
$MainAfter = ((& git -C $Repo ls-remote $Remote 'refs/heads/main') -split "`t")[0].Trim()
if ($MainAfter -ne $MainBefore) { throw "main 意外变化：$MainBefore -> $MainAfter" }
Write-Host "EXEDRA-TEST 已覆盖：$NewWorkerSha"
Write-Host "main 未改动：$MainAfter"

Write-Host ''
Write-Host '[6/6] 等待 GitHub Actions 和线上 Worker……'
$Run = $null
for ($Attempt = 1; $Attempt -le 120; $Attempt++) {
    $json = & gh run list --repo $GitHubRepo --workflow $Workflow --branch $Target --limit 20 `
        --json databaseId,headSha,status,conclusion,createdAt
    if ($LASTEXITCODE -ne 0) { throw '无法读取 GitHub Actions 状态。' }
    $Run = @($json | ConvertFrom-Json) |
        Where-Object { $_.headSha -eq $NewWorkerSha } |
        Sort-Object createdAt -Descending |
        Select-Object -First 1
    if (-not $Run) {
        Write-Host "等待 Action 创建：$Attempt/120"
        Start-Sleep -Seconds 5
        continue
    }
    $conclusion = if ($Run.conclusion) { $Run.conclusion } else { '-' }
    Write-Host "Action $($Run.databaseId): $($Run.status) / $conclusion"
    if ($Run.status -eq 'completed') {
        if ($Run.conclusion -ne 'success') {
            & gh run view $Run.databaseId --repo $GitHubRepo --log-failed
            throw "Worker 构建失败：Run $($Run.databaseId)"
        }
        break
    }
    Start-Sleep -Seconds 10
}
if (-not $Run -or $Run.status -ne 'completed') { throw '等待 GitHub Actions 完成超时。' }

$Config = $null
$Online = $false
for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
    try {
        $Config = Invoke-RestMethod -Uri "$Site/api/proofreading/config?revision=$NewWorkerSha-$Attempt" -TimeoutSec 30
        if ($Config.source_revision -eq $NewWorkerSha) { $Online = $true; break }
    } catch {}
    Write-Host "等待线上版本：$Attempt/60"
    Start-Sleep -Seconds 10
}
if (-not $Online) { throw "线上 Worker 未切换到 $NewWorkerSha" }
$OnlineStories = @(Invoke-RestMethod -Uri "$Site/story_index.json?revision=$NewWorkerSha" -TimeoutSec 120)
$OnlineOfficial = @($OnlineStories | Where-Object { $_.official_tw -eq $true })
if ($OnlineOfficial.Count -ne $OfficialStories.Count) {
    throw "线上台服标记数量异常：$($OnlineOfficial.Count) != $($OfficialStories.Count)"
}
foreach ($scope in @('magireco', 'exedra')) {
    $value = Invoke-RestMethod -Uri "$Site/search_index_manifest.$scope.json?revision=$NewWorkerSha" -TimeoutSec 60
    if (-not $value.object_key -or $value.object_key -notlike "search/$scope/*") {
        throw "线上拆分搜索 manifest 异常：$scope"
    }
}

Write-Host ''
Write-Host '=================================================='
Write-Host '全部目标已完成并通过线上验证'
Write-Host "提交：$NewWorkerSha"
Write-Host "台服官方剧情组：$($OnlineOfficial.Count)"
Write-Host '台服 Scenario 注入：2780/2780'
Write-Host '章节名：getFieldStageMstList'
Write-Host '小节名：getAdvMstList'
Write-Host '侧栏宽度：可拖动并持久化'
Write-Host '阅读设置：PC 端已加宽'
Write-Host '全文搜索：全魔法纪录 / 全 Exedra 两组对象'
Write-Host "网站：$Site"
Write-Host "main：$MainAfter（未改动）"
Write-Host '=================================================='
