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
        private const string OutputApkPath = "build/ARServiceAssistant.apk";

        private const string KeystorePathEnvVar = "ARSA_KEYSTORE_PATH";
        private const string KeystorePasswordEnvVar = "ARSA_KEYSTORE_PASSWORD";
        private const string KeyaliasNameEnvVar = "ARSA_KEYALIAS_NAME";
        private const string KeyaliasPasswordEnvVar = "ARSA_KEYALIAS_PASSWORD";

        public static void BuildAndroid()
        {
            ConfigureKeystore();

            var outputDirectory = Path.GetDirectoryName(OutputApkPath);
            if (!string.IsNullOrEmpty(outputDirectory) && !Directory.Exists(outputDirectory))
            {
                Directory.CreateDirectory(outputDirectory);
            }

            var scenes = Array.ConvertAll(EditorBuildSettings.scenes, scene => scene.path);
            var options = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = OutputApkPath,
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
