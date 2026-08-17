using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEngine;

namespace ARSA.Build
{
    /// <summary>
    /// CLI/CI entry point for building the Android APK. Invoked by `make apk` (see
    /// the repo root Makefile) via `-executeMethod ARSA.Build.BuildScript.BuildAndroid`.
    /// The release keystore itself is never committed — its path and passwords come
    /// entirely from environment variables.
    /// </summary>
    public static class BuildScript
    {
        // "Build/ARServiceAssistant.apk" *inside the Unity project* — not repo-root
        // "build/". Resolved from Application.dataPath rather than a bare relative
        // string, so it lands in the same place regardless of the process's working
        // directory when invoked (batchmode's CWD behavior isn't something to rely
        // on implicitly). unity/[Bb]uild/ is already gitignored.
        private const string OutputApkFileName = "ARServiceAssistant.apk";

        private const string KeystorePathEnvVar = "ARSA_KEYSTORE_PATH";
        private const string KeystorePasswordEnvVar = "ARSA_KEYSTORE_PASSWORD";
        private const string KeyaliasNameEnvVar = "ARSA_KEYALIAS_NAME";
        private const string KeyaliasPasswordEnvVar = "ARSA_KEYALIAS_PASSWORD";

        public static void BuildAndroid()
        {
            ConfigureKeystore();
            try
            {
                var projectRoot = Directory.GetParent(Application.dataPath)!.FullName;
                var outputDirectory = Path.Combine(projectRoot, "Build");
                var outputPath = Path.Combine(outputDirectory, OutputApkFileName);
                if (!Directory.Exists(outputDirectory))
                {
                    Directory.CreateDirectory(outputDirectory);
                }

                var scenes = Array.ConvertAll(EditorBuildSettings.scenes, scene => scene.path);
                var options = new BuildPlayerOptions
                {
                    scenes = scenes,
                    locationPathName = outputPath,
                    target = BuildTarget.Android,
                    options = BuildOptions.None,
                };

                var report = BuildPipeline.BuildPlayer(options);
                var summary = report.summary;

                if (summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded)
                {
                    throw new BuildFailedException(
                        $"Android build failed: {summary.result} ({summary.totalErrors} error(s)).");
                }

                Debug.Log($"Android build succeeded: {summary.outputPath} ({summary.totalSize} bytes).");
            }
            finally
            {
                // PlayerSettings.Android.keystoreName/keyaliasName are project-level
                // (not build-scoped) and get written straight to the committed
                // ProjectSettings.asset the moment ConfigureKeystore sets them —
                // there's no "this build only" variant. Clear them back out
                // afterward so the repo never carries a record of which keystore
                // built it, success or failure.
                PlayerSettings.Android.useCustomKeystore = false;
                PlayerSettings.Android.keystoreName = string.Empty;
                PlayerSettings.Android.keystorePass = string.Empty;
                PlayerSettings.Android.keyaliasName = string.Empty;
                PlayerSettings.Android.keyaliasPass = string.Empty;
                AssetDatabase.SaveAssets();
            }
        }

        private static void ConfigureKeystore()
        {
            var keystorePath = Environment.GetEnvironmentVariable(KeystorePathEnvVar);
            if (string.IsNullOrEmpty(keystorePath))
            {
                throw new BuildFailedException(
                    $"{KeystorePathEnvVar} is not set. It must point at the release keystore " +
                    "(never committed to this repository).");
            }

            if (!File.Exists(keystorePath))
            {
                throw new BuildFailedException($"Keystore not found at '{keystorePath}' ({KeystorePathEnvVar}).");
            }

            PlayerSettings.Android.useCustomKeystore = true;
            PlayerSettings.Android.keystoreName = keystorePath;
            PlayerSettings.Android.keystorePass = Environment.GetEnvironmentVariable(KeystorePasswordEnvVar) ?? string.Empty;
            PlayerSettings.Android.keyaliasName = Environment.GetEnvironmentVariable(KeyaliasNameEnvVar) ?? string.Empty;
            PlayerSettings.Android.keyaliasPass = Environment.GetEnvironmentVariable(KeyaliasPasswordEnvVar) ?? string.Empty;
        }
    }
}
