import { TreeStateProvider } from "@/components/common/TreeStateContext";
import PracticePanel from "@/components/panels/practice/PracticePanel";

export default function PracticePage() {
  return (
    <TreeStateProvider id="practice">
      <PracticePanel />
    </TreeStateProvider>
  );
}
