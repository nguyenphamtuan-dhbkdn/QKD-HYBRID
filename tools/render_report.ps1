param(
    [string]$InputFile = 'docs/BaoCao_QKD_Hybrid_MoRong.docx',
    [string]$OutputFile = 'docs/BaoCao_QKD_Hybrid_MoRong.pdf',
    [string]$OutputDirectory = 'results/report_build/expanded_render'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$inputPath = Join-Path $taskRoot $InputFile
$renderPath = Join-Path $taskRoot $OutputDirectory
New-Item -ItemType Directory -Force -Path $renderPath | Out-Null
$pdfPath = Join-Path $taskRoot $OutputFile
$wordApp = New-Object -ComObject Word.Application
$wordApp.Visible = $false
$wordApp.DisplayAlerts = 0
$reportDoc = $null
try {
    $reportDoc = $wordApp.Documents.Open($inputPath, $false, $false)
    $wordApp.ActiveWindow.View.Type = 3
    # A second pass is needed because populated lists change pagination.
    for ($pass = 0; $pass -lt 3; $pass++) {
        $reportDoc.Fields.Update() | Out-Null
        foreach ($toc in $reportDoc.TablesOfContents) { $toc.Update() }
        foreach ($list in $reportDoc.TablesOfFigures) { $list.Update() }
        $reportDoc.Repaginate()
    }
    $reportDoc.Save()
    $reportDoc.ExportAsFixedFormat($pdfPath, 17)
    # Export forces print pagination; refresh references against that layout.
    $reportDoc.Repaginate()
    foreach ($toc in $reportDoc.TablesOfContents) { $toc.UpdatePageNumbers() }
    foreach ($list in $reportDoc.TablesOfFigures) { $list.UpdatePageNumbers() }
    $reportDoc.Save()
    $reportDoc.ExportAsFixedFormat($pdfPath, 17)
    $sectionInfo = @()
    foreach ($section in $reportDoc.Sections) {
        $startRange = $section.Range.Duplicate
        $startRange.Collapse(1)
        $sectionInfo += [ordered]@{
            index = $section.Index
            physical_start = $startRange.Information(3)
            logical_start = $startRange.Information(1)
            header = $section.Headers.Item(1).Range.Text.Trim()
            footer = $section.Footers.Item(1).Range.Text.Trim()
            header_linked = $section.Headers.Item(1).LinkToPrevious
            footer_linked = $section.Footers.Item(1).LinkToPrevious
        }
    }
    $navigation = @()
    $listIndex = 0
    foreach ($list in @($reportDoc.TablesOfContents) + @($reportDoc.TablesOfFigures)) {
        $listIndex++
        $links = @()
        foreach ($link in $list.Range.Hyperlinks) {
            $anchor = $link.SubAddress
            $exists = $reportDoc.Bookmarks.Exists($anchor)
            $targetPage = $null
            $targetText = ''
            if ($exists) {
                $target = $reportDoc.Bookmarks.Item($anchor).Range.Duplicate
                $targetText = $target.Text.Trim()
                if ($target.End -gt $target.Start) { $target.MoveStart(1, 1) | Out-Null }
                $target.Collapse(1)
                $targetPage = $target.Information(1)
            }
            $links += [ordered]@{
                text = $link.Range.Text.Trim()
                anchor = $anchor
                target_exists = $exists
                target_page = $targetPage
                target_text = $targetText
            }
        }
        $navigation += [ordered]@{ index = $listIndex; links = $links }
    }
    $pageCount = $reportDoc.ComputeStatistics(2)
    $reportDoc.Close(0)
    $reportDoc = $null
    $audit = [ordered]@{
        pages = $pageCount
        docx_sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLower()
        pdf_sha256 = (Get-FileHash -LiteralPath $pdfPath -Algorithm SHA256).Hash.ToLower()
        sections = $sectionInfo
        navigation = $navigation
    }
    $audit | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $renderPath 'word_audit.json') -Encoding utf8
    Write-Output ('Pages=' + $audit.pages)
    Write-Output $pdfPath
} finally {
    if ($null -ne $reportDoc) { $reportDoc.Close(0) }
    $wordApp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordApp) | Out-Null
}
