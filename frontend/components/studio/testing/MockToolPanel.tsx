'use client'

// Test-only tool used by the Stage 8.7 scalability check. Registered ONLY when
// the build sets NEXT_PUBLIC_E2E_MOCK_TOOL=true (see lib/registries/panels.tsx);
// a normal build never references this module. The marker string below is what
// the build check greps for to prove that.
export const MOCK_TOOL_MARKER = 'narratiq-e2e-mock-tool-7f3a'

export default function MockToolPanel() {
  return (
    <div className="p-6 text-sm text-[#cdd2f0]" data-testid="mock-tool-panel" data-marker={MOCK_TOOL_MARKER}>
      <h2 className="text-base font-medium text-[#e8eaf6] mb-2">Mock tool</h2>
      <p>A stand-in for the next feature. If this renders without layout changes, adding a tool needed no redesign.</p>
    </div>
  )
}
