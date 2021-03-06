# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for the experimental input pipeline ops."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np

from tensorflow.contrib.data.python.kernel_tests import dataset_serialization_test_base
from tensorflow.contrib.data.python.ops import interleave_ops
from tensorflow.python.data.ops import dataset_ops
from tensorflow.python.framework import errors
from tensorflow.python.framework import random_seed
from tensorflow.python.platform import test


class DirectedInterleaveDatasetTest(test.TestCase):

  def testBasic(self):
    selector_dataset = dataset_ops.Dataset.range(10).repeat(100)
    input_datasets = [
        dataset_ops.Dataset.from_tensors(i).repeat(100) for i in range(10)
    ]
    dataset = interleave_ops.DirectedInterleaveDataset(selector_dataset,
                                                       input_datasets)
    iterator = dataset.make_initializable_iterator()
    next_element = iterator.get_next()

    with self.test_session() as sess:
      sess.run(iterator.initializer)
      for _ in range(100):
        for i in range(10):
          self.assertEqual(i, sess.run(next_element))
      with self.assertRaises(errors.OutOfRangeError):
        sess.run(next_element)

  def _normalize(self, vec):
    return vec / vec.sum()

  def _chi2(self, expected, actual):
    actual = np.asarray(actual)
    expected = np.asarray(expected)
    diff = actual - expected
    chi2 = np.sum(diff * diff / expected, axis=0)
    return chi2

  def _testSampleFromDatasetsHelper(self, weights, num_datasets, num_samples):
    # Create a dataset that samples each integer in `[0, num_datasets)`
    # with probability given by `weights[i]`.
    dataset = interleave_ops.sample_from_datasets([
        dataset_ops.Dataset.from_tensors(i).repeat(None)
        for i in range(num_datasets)
    ], weights)
    dataset = dataset.take(num_samples)
    iterator = dataset.make_one_shot_iterator()
    next_element = iterator.get_next()

    with self.test_session() as sess:
      freqs = np.zeros([num_datasets])
      for _ in range(num_samples):
        freqs[sess.run(next_element)] += 1
      with self.assertRaises(errors.OutOfRangeError):
        sess.run(next_element)

    return freqs

  def testSampleFromDatasets(self):
    random_seed.set_random_seed(1619)
    num_samples = 5000
    rand_probs = self._normalize(np.random.random_sample((15,)))

    # Use chi-squared test to assert that the observed distribution matches the
    # expected distribution. Based on the implementation in
    # "tensorflow/python/kernel_tests/multinomial_op_test.py".
    for probs in [[.85, .05, .1], rand_probs]:
      probs = np.asarray(probs)
      classes = len(probs)
      freqs = self._testSampleFromDatasetsHelper(probs, classes, num_samples)
      self.assertLess(self._chi2(probs, freqs / num_samples), 1e-2)

      # Also check that `weights` as a dataset samples correctly.
      probs_ds = dataset_ops.Dataset.from_tensors(probs).repeat()
      freqs = self._testSampleFromDatasetsHelper(probs_ds, classes, num_samples)
      self.assertLess(self._chi2(probs, freqs / num_samples), 1e-2)

  def testSelectFromDatasets(self):
    words = [b"foo", b"bar", b"baz"]
    datasets = [dataset_ops.Dataset.from_tensors(w).repeat() for w in words]
    choice_array = np.random.randint(3, size=(15,), dtype=np.int64)
    choice_dataset = dataset_ops.Dataset.from_tensor_slices(choice_array)
    dataset = interleave_ops.choose_from_datasets(datasets, choice_dataset)
    iterator = dataset.make_one_shot_iterator()
    next_element = iterator.get_next()

    with self.test_session() as sess:
      for i in choice_array:
        self.assertEqual(words[i], sess.run(next_element))
      with self.assertRaises(errors.OutOfRangeError):
        sess.run(next_element)

  def testErrors(self):
    with self.assertRaisesRegexp(ValueError,
                                 r"vector of length `len\(datasets\)`"):
      interleave_ops.sample_from_datasets(
          [dataset_ops.Dataset.range(10),
           dataset_ops.Dataset.range(20)],
          weights=[0.25, 0.25, 0.25, 0.25])

    with self.assertRaisesRegexp(TypeError, "`tf.float32` or `tf.float64`"):
      interleave_ops.sample_from_datasets(
          [dataset_ops.Dataset.range(10),
           dataset_ops.Dataset.range(20)],
          weights=[1, 1])

    with self.assertRaisesRegexp(TypeError, "must have the same type"):
      interleave_ops.sample_from_datasets([
          dataset_ops.Dataset.from_tensors(0),
          dataset_ops.Dataset.from_tensors(0.0)
      ])

    with self.assertRaisesRegexp(TypeError, "tf.int64"):
      interleave_ops.choose_from_datasets([
          dataset_ops.Dataset.from_tensors(0),
          dataset_ops.Dataset.from_tensors(1)
      ], choice_dataset=dataset_ops.Dataset.from_tensors(1.0))

    with self.assertRaisesRegexp(TypeError, "scalar"):
      interleave_ops.choose_from_datasets([
          dataset_ops.Dataset.from_tensors(0),
          dataset_ops.Dataset.from_tensors(1)
      ], choice_dataset=dataset_ops.Dataset.from_tensors([1.0]))


class SampleFromDatasetsSerializationTest(
    dataset_serialization_test_base.DatasetSerializationTestBase):

  def _build_dataset(self, probs, num_samples):
    dataset = interleave_ops.sample_from_datasets(
        [
            dataset_ops.Dataset.from_tensors(i).repeat(None)
            for i in range(len(probs))
        ],
        probs,
        seed=1813)
    return dataset.take(num_samples)

  def testSerializationCore(self):
    self.run_core_tests(
        lambda: self._build_dataset([0.5, 0.5], 100),
        lambda: self._build_dataset([0.25, 0.25, 0.25, 0.25], 1000), 100)


if __name__ == "__main__":
  test.main()
