export function isInterviewTerminal(status: string): boolean {
  return status === "finished" || status === "cancelled";
}

export function canCancelInterview(status: string): boolean {
  return status === "created" || status === "running";
}

export function snapshotStatus(snapshot: { finished: boolean; cancelled?: boolean; state: string }): "active" | "finished" | "cancelled" {
  return snapshot.cancelled || snapshot.state === "cancelled" ? "cancelled" : snapshot.finished ? "finished" : "active";
}
