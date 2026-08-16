using UnityEngine;

namespace ARSA.Core
{
    /// <summary>
    /// All runtime configuration for the client: which edge server to talk to, how
    /// often to poll it, and the safety thresholds from ADR-0006. A ScriptableObject
    /// asset, never constants baked into a MonoBehaviour (see CLAUDE.md section 7) —
    /// so the same client build can point at a different server/object just by
    /// swapping the asset.
    /// </summary>
    [CreateAssetMenu(fileName = "ArsaConfig", menuName = "ARSA/Config", order = 0)]
    public sealed class ArsaConfig : ScriptableObject
    {
        [Header("Edge server (LAN only — see CLAUDE.md section 2)")]
        [SerializeField] private string serverHost = "192.168.1.50";
        [SerializeField] private int serverPort = 8000;

        [Header("Client")]
        [Tooltip("How often the client polls/streams frames to the edge server, in Hz.")]
        [SerializeField] private float refreshRateHz = 10f;

        [Header("Safety thresholds (see ADR-0006)")]
        [Tooltip("Below this part-recognition confidence, the client must refuse rather than guess.")]
        [SerializeField] private float minPartConfidence = 0.65f;
        [Tooltip("Below this retrieval score, the client must say the manual has nothing on it.")]
        [SerializeField] private float minRetrievalScore = 0.35f;

        public string ServerHost => serverHost;
        public int ServerPort => serverPort;
        public float RefreshRateHz => refreshRateHz;
        public float MinPartConfidence => minPartConfidence;
        public float MinRetrievalScore => minRetrievalScore;

        /// <summary>
        /// Checks every field against the ranges documented in .env.example /
        /// object.yaml. Returns false with a human-readable reason instead of
        /// throwing, so callers (including OnValidate) can decide what to do.
        /// </summary>
        public bool Validate(out string error)
        {
            if (string.IsNullOrWhiteSpace(serverHost))
            {
                error = "serverHost must not be empty.";
                return false;
            }

            if (serverPort < 1 || serverPort > 65535)
            {
                error = $"serverPort must be in [1, 65535], was {serverPort}.";
                return false;
            }

            if (refreshRateHz <= 0f)
            {
                error = $"refreshRateHz must be > 0, was {refreshRateHz}.";
                return false;
            }

            if (minPartConfidence < 0f || minPartConfidence > 1f)
            {
                error = $"minPartConfidence must be in [0, 1], was {minPartConfidence}.";
                return false;
            }

            if (minRetrievalScore < 0f || minRetrievalScore > 1f)
            {
                error = $"minRetrievalScore must be in [0, 1], was {minRetrievalScore}.";
                return false;
            }

            error = null;
            return true;
        }

        private void OnValidate()
        {
            if (!Validate(out var error))
            {
                Debug.LogWarning($"{name}: {error}", this);
            }
        }
    }
}
