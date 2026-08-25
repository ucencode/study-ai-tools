import { useEffect } from "react";

export const BASE_TITLE = "Study Tools";

/**
 * Last writer wins, so exactly one component may own the title at a time: JobDetail
 * while a job is open, the jobs rail whenever one isn't. Pass null to own nothing.
 */
export function useDocumentTitle(title) {
  useEffect(() => {
    if (title === null) return;
    document.title = title;
  }, [title]);
}
