using ARSA.Core;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace ARSA.Tests.EditMode
{
    public sealed class ConfigTests
    {
        private ArsaConfig config;

        [SetUp]
        public void SetUp()
        {
            config = ScriptableObject.CreateInstance<ArsaConfig>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(config);
        }

        [Test]
        public void DefaultValues_AreValid()
        {
            Assert.IsTrue(config.Validate(out var error), error);
        }

        [Test]
        public void InvalidPort_FailsValidation()
        {
            var serialized = new SerializedObject(config);
            serialized.FindProperty("serverPort").intValue = 0;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            var isValid = config.Validate(out var error);

            Assert.IsFalse(isValid);
            StringAssert.Contains("serverPort", error);
        }

        [Test]
        public void InvalidMinPartConfidence_FailsValidation()
        {
            var serialized = new SerializedObject(config);
            serialized.FindProperty("minPartConfidence").floatValue = 1.5f;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            var isValid = config.Validate(out var error);

            Assert.IsFalse(isValid);
            StringAssert.Contains("minPartConfidence", error);
        }
    }
}
