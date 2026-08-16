using System;
using System.Collections.Generic;
using UnityEngine;

namespace ARSA.Core
{
    /// <summary>
    /// Loads user-facing strings from Assets/Resources/Strings/ — German first,
    /// English fallback (see CLAUDE.md section 2). No user-facing string may be
    /// hardcoded in code; every one goes through <see cref="Get"/> instead.
    /// </summary>
    public static class Strings
    {
        private const string DefaultLanguage = "de";
        private const string FallbackLanguage = "en";

        private static Dictionary<string, string> currentTable;
        private static string loadedLanguage;

        /// <summary>Looks up <paramref name="key"/> in the German table, falling back to English.</summary>
        public static string Get(string key)
        {
            EnsureLoaded(DefaultLanguage);
            if (currentTable != null && currentTable.TryGetValue(key, out var value))
            {
                return value;
            }

            EnsureLoaded(FallbackLanguage);
            if (currentTable != null && currentTable.TryGetValue(key, out value))
            {
                return value;
            }

            Debug.LogWarning($"Strings: missing key '{key}' in both '{DefaultLanguage}' and '{FallbackLanguage}'.");
            return key;
        }

        private static void EnsureLoaded(string language)
        {
            if (loadedLanguage == language && currentTable != null)
            {
                return;
            }

            var asset = Resources.Load<TextAsset>($"Strings/strings_{language}");
            if (asset == null)
            {
                Debug.LogError($"Strings: 'Resources/Strings/strings_{language}.json' not found.");
                currentTable = null;
                loadedLanguage = null;
                return;
            }

            var table = JsonUtility.FromJson<StringTable>(asset.text);
            currentTable = new Dictionary<string, string>();
            if (table?.entries != null)
            {
                foreach (var entry in table.entries)
                {
                    currentTable[entry.key] = entry.value;
                }
            }

            loadedLanguage = language;
        }

        [Serializable]
        private struct Entry
        {
            public string key;
            public string value;
        }

        [Serializable]
        private sealed class StringTable
        {
            public Entry[] entries;
        }
    }
}
