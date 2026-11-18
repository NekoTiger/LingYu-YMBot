$ErrorActionPreference = 'Stop'
$base = Split-Path $PSScriptRoot -Parent
$qa = Join-Path $PSScriptRoot '汇报表更新_20261118'
$source = Join-Path $base '提交版/灵驭_中期汇报表.docx'
$legacy = Join-Path $base '提交版/灵驭_中期汇报表.doc'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $null
try {
    $doc = $word.Documents.Open($source,$false,$true)
    $doc.Repaginate()
    $pages = $doc.ComputeStatistics(2)
    $sourceText = $doc.Content.Text
    $doc.ExportAsFixedFormat((Join-Path $qa 'report_docx.pdf'),17)
    $doc.SaveAs2($legacy,0)
    $doc.Close(0)
    $doc = $word.Documents.Open($legacy,$false,$true)
    $doc.Repaginate()
    $legacyPages = $doc.ComputeStatistics(2)
    if ($sourceText -ne $doc.Content.Text) { throw 'DOC and DOCX text differ' }
    $doc.ExportAsFixedFormat((Join-Path $qa 'report_doc.pdf'),17)
    $doc.Close(0)
    $doc = $null
    @{ docx_pages=$pages; doc_pages=$legacyPages; text_equal=$true; renderer='Microsoft Word native export'; date='2026-11-18' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $qa 'native_verification.json') -Encoding UTF8
    Write-Output "DOCX pages: $pages; DOC pages: $legacyPages; text identical"
} finally {
    if ($null -ne $doc) { $doc.Close(0) }
    $word.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
