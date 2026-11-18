$ErrorActionPreference = 'Stop'
$build = $PSScriptRoot
$base = Split-Path $build -Parent
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $report = $word.Documents.Open((Join-Path $base '提交版/灵驭_中期汇报表.docx'),$false,$true)
    $report.ExportAsFixedFormat((Join-Path $build 'report.pdf'),17)
    $report.SaveAs2((Join-Path $base '提交版/灵驭_中期汇报表.doc'),0)
    'Report pages: ' + $report.ComputeStatistics(2)
    $report.Close(0)
} finally { $word.Quit() }

$powerpoint = New-Object -ComObject PowerPoint.Application
$powerpoint.DisplayAlerts = 1
try {
    $deck = $powerpoint.Presentations.Open((Join-Path $build 'candidate.pptx'),$false,$false,$false)
    $s = $deck.Slides.Item(2)
    # Embedded local video replaces the task poster, preserving the same 16:9 frame.
    for ($i=$s.Shapes.Count; $i -ge 1; $i--) {
        $shape = $s.Shapes.Item($i)
        if ($shape.Type -eq 13 -and [Math]::Abs($shape.Left-48) -lt 1) { $shape.Delete() }
    }
    $movie = $s.Shapes.AddMediaObject2((Join-Path $build 'assets/task_excerpt.mp4'),$false,$true,48,161.25,600,337.5)
    $movie.Name = '25秒仿真任务原速节选'
    $movie.AnimationSettings.PlaySettings.PlayOnEntry = -1
    $movie.AnimationSettings.PlaySettings.HideWhileNotPlaying = 0
    $movie.AnimationSettings.PlaySettings.RewindMovie = -1
    for ($i=9; $i -le 12; $i++) { $deck.Slides.Item($i).SlideShowTransition.Hidden = -1 }
    $deck.SaveAs((Join-Path $build 'candidate_native.pptx'),24)
    $native = Join-Path $build 'native-render'
    New-Item -ItemType Directory -Force $native | Out-Null
    for ($i=1; $i -le $deck.Slides.Count; $i++) {
        $deck.Slides.Item($i).Export((Join-Path $native ('slide-{0:D2}.png' -f $i)),'PNG',1280,720)
    }
    'Native slides: '+$deck.Slides.Count
    'Embedded video duration ms: '+$movie.MediaFormat.Length
    $deck.Close()
} finally { $powerpoint.Quit() }
