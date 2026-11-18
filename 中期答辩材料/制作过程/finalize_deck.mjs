import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const skill='C:/Users/10141/.codex/plugins/cache/openai-primary-runtime/presentations/26.1112.11217/skills/presentations';
const runtime='C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1112-737-0_26.1112.737.0_x64__3k8sg7r9htsxt/dependencies';
process.env.RUNTIME_NODE_MODULES=path.join(runtime,'node/node_modules');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({
 workspaceDir:path.resolve(here,'..'),candidatePath:path.join(here,'candidate_ready.pptx'),
 finalPath:path.resolve(here,'../提交版/灵驭_中期答辩_正式版.pptx'),
 pythonExecutable:path.join(runtime,'python/python.exe'),
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...[3,7,9,11].flatMap(n=>['--require-native-table-slide',String(n)])],
 explicitTotalSlideCount:12,requiredNativeTableOwnerSlides:[3,7,9,11],requiredNativeChartOwnerSlides:[4,5],
 materializeLiteralChartWorkbooks:true,nativeChartTargetApplication:'powerpoint',
 fontPolicy:{basis:'design',families:['Microsoft YaHei']},
 verifyArtifactToolImport:true,receiptPath:path.join(here,'final_validation_v3.json')
});
console.log(JSON.stringify({finalPath:result.finalPath,sha256:result.finalSha256,integrity:result.packageIntegrity.status,layoutFindings:result.presentationLayout.findingCount,warnings:result.presentationLayout.warnings,importPassed:result.firstPartyImport.passed,chartsPassed:result.nativeChartValidation.passed},null,2));
