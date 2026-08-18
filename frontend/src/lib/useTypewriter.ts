import { useEffect, useState } from "react";

/** speedMs <= 0 renders `text` immediately with no animation, so callers can reuse
 * this hook for both the actively-typing message and already-settled ones. */
export function useTypewriter(text: string, speedMs = 18) {
  const [shown, setShown] = useState(speedMs <= 0 ? text : "");
  useEffect(() => {
    if (speedMs <= 0) {
      setShown(text);
      return;
    }
    setShown("");
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, speedMs);
    return () => clearInterval(id);
  }, [text, speedMs]);
  return shown;
}
