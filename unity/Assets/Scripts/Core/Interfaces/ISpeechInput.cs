namespace ARSA.Core
{
    /// <summary>
    /// Seam between the AR client and the microphone: the Quest 3S's mic at
    /// runtime, a canned audio clip in tests. Keeping this as an interface is what
    /// lets the rest of the client be tested without a headset or microphone
    /// hardware (see CLAUDE.md section 7).
    ///
    /// Deliberately empty for now — no implementation exists yet. Adding one is a
    /// separate task.
    /// </summary>
    public interface ISpeechInput
    {
    }
}
