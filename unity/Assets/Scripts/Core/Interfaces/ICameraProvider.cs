namespace ARSA.Core
{
    /// <summary>
    /// Seam between the AR client and whatever supplies camera frames: the Quest
    /// 3S's passthrough camera at runtime, a fixed sequence of frames in EditMode
    /// tests. Keeping this as an interface is what lets the rest of the client be
    /// tested without a headset (see CLAUDE.md section 7).
    ///
    /// Deliberately empty for now — no implementation exists yet. Adding one is a
    /// separate task; see ARSA.Camera.
    /// </summary>
    public interface ICameraProvider
    {
    }
}
