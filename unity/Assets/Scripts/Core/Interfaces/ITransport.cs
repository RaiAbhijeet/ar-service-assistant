namespace ARSA.Core
{
    /// <summary>
    /// Seam between the AR client and the edge server: a WebSocket over the LAN at
    /// runtime, a fake transport in tests. Keeping this as an interface is what lets
    /// the rest of the client be tested without a live edge server (see CLAUDE.md
    /// section 7).
    ///
    /// Deliberately empty for now — no implementation exists yet. Adding one is a
    /// separate task; see ARSA.Net.
    /// </summary>
    public interface ITransport
    {
    }
}
