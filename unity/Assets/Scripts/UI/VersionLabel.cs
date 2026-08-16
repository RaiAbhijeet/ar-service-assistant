using ARSA.Core;
using TMPro;
using UnityEngine;

namespace ARSA.UI
{
    /// <summary>
    /// Binds <see cref="Application.version"/> into the world-anchored TMP panel in
    /// Assets/Scenes/Main.unity, via the German-first "app_version_label" string
    /// resource. Runs once on enable, not per frame.
    /// </summary>
    [RequireComponent(typeof(TextMeshProUGUI))]
    public sealed class VersionLabel : MonoBehaviour
    {
        private TextMeshProUGUI label;

        private void Awake()
        {
            label = GetComponent<TextMeshProUGUI>();
        }

        private void OnEnable()
        {
            label.text = string.Format(Strings.Get("app_version_label"), Application.version);
        }
    }
}
