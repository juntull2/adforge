# Reference editor implementation

Approved objective: reference video + unchanged new script + local media -> editable CapCut project and native export verification. Keep source projects and Notion human-owned fields untouched.

Ruling: use the installed pyCapCut only behind a new renderer. Replace editing decisions rather than rewriting unrelated A-grade and Notion workflows.
Ruling: use PySceneDetect for scene boundaries and vision observations for source selection. Keep WhisperX isolated and optional because torch is absent; expose missing alignment as a review issue instead of fabricating word timing.
Ruling: mine exact materials from local drafts, inspired by MIT capcut-mcp, with no upstream code vendoring. A cache hit is not proof of successful native rendering.
Ruling: stage all drafts and reports in the workspace. Copy only newly generated projects to the CapCut draft directory on explicit app action; never overwrite existing projects or force-close CapCut.

Verification: 16 tests passed, including invalid caption times, explicit-versus-observed resource selection, and native effect-track attachment; compileall passed for app and new editor.
Native smoke: CapCut 9.5 launched, but UI Automation returned only HomeWindow without actionable children. Automatic open/export is not verified on this installation. Manual native-export upload is supported for inspection. No genuine reference/API quality run or native-effect playback verification has been performed.
Review fixes: retain native animation cloud IDs; use effect tracks for apply_target_type=2; assign caption position by midpoint; reject absent selected resources; honor visual verdict booleans; persist failed native reviews; never infer reference effects from cache popularity.
