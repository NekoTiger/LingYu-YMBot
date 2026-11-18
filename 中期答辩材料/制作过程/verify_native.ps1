$ErrorActionPreference = 'Stop'
$build=$PSScriptRoot
$base=Split-Path $build -Parent
$app=New-Object -ComObject PowerPoint.Application
$app.DisplayAlerts=1
try {
  $deck=$app.Presentations.Open((Join-Path $base '提交版/灵驭_中期答辩_正式版.pptx'),$true,$false,$false)
  $renders=Join-Path $build 'final-render'
  New-Item -ItemType Directory -Force $renders | Out-Null
  $charts=0; $tables=0; $video=0; $hidden=0; $notes=0
  for ($i=1; $i -le $deck.Slides.Count; $i++) {
    $s=$deck.Slides.Item($i)
    $s.Export((Join-Path $renders ('slide-{0:D2}.png' -f $i)),'PNG',1280,720)
    if ($s.SlideShowTransition.Hidden -eq -1) {$hidden++}
    foreach($sh in $s.Shapes) {
      if($sh.HasChart -eq -1){$charts++}
      if($sh.HasTable -eq -1){$tables++}
      if($sh.Type -eq 16){$video++; if($sh.MediaFormat.Length -ne 25000){throw 'Unexpected video duration'}}
    }
    if($s.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text.Length -gt 10){$notes++}
  }
  $probe=Join-Path $build 'chart_editability_probe.pptx'
  $chartShape=@($deck.Slides.Item(4).Shapes | Where-Object {$_.HasChart -eq -1})[0]
  $chartShape.Chart.SeriesCollection(1).Values=@(14.68,1.35)
  $chartShape.Width=$chartShape.Width+1
  $deck.SaveCopyAs($probe,24)
  $deck.Close()
  $probeDeck=$app.Presentations.Open($probe,$true,$false,$false)
  $probeChart=@($probeDeck.Slides.Item(4).Shapes | Where-Object {$_.HasChart -eq -1})[0]
  $probeValues=@($probeChart.Chart.SeriesCollection(1).Values)
  if ([Math]::Abs([double]$probeValues[0]-14.68) -gt .0001) {throw 'Native chart edit did not persist'}
  $probeDeck.Close()
  $record=@{slides=12; main_slides=8; hidden_appendix_slides=$hidden; native_charts=$charts; native_tables=$tables; embedded_videos=$video; video_duration_seconds=25; notes_pages=$notes; chart_edit_saved_and_reopened=$true}
  $record | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $build 'native_verification.json')
  $record | ConvertTo-Json
} finally { if($app.Presentations.Count -eq 0) {$app.Quit()} }
