from pathlib import Path
from typing import Optional, Callable, Union, Mapping, Sequence

import numpy as np
import torch.nn as nn
import torch.optim

from src.metrics.divahisdb import HisDBIoU
from src.tasks.semantic_segmentation.utils.output_tools import _get_argmax
from src.tasks.base_task import AbstractTask
from src.utils import template_utils
from src.tasks.utils.outputs import OutputKeys

log = template_utils.get_logger(__name__)


class SemanticSegmentation(AbstractTask):

    def __init__(self,
                 model: nn.Module,
                 optimizer: torch.optim.Optimizer,
                 loss_fn: Optional[Callable] = None,
                 metric_train: Optional[Union[Callable, Mapping, Sequence, None]] = None,
                 metric_val: Optional[Union[Callable, Mapping, Sequence, None]] = None,
                 metric_test: Optional[Union[Callable, Mapping, Sequence, None]] = None,
                 test_output_path: Optional[Union[str, Path]] = 'output',
                 lr: float = 1e-3
                 ) -> None:
        """
        pixelvise semantic segmentation. The output of the network during test is a DIVAHisDB encoded image

        :param model: torch.nn.Module
            The encoder for the segmentation e.g. unet
        :param test_output_path: str
            String with a path to the output folder of the testing
        """
        if loss_fn is None:
            loss_fn = nn.CrossEntropyLoss()

        super().__init__(
            model=model,
            optimizer=optimizer,
            loss_fn=loss_fn,
            metric_train=metric_train,
            metric_val=metric_val,
            metric_test=metric_test,
            test_output_path=test_output_path,
            lr=lr
        )
        self.save_hyperparameters()

        # paths
        self.test_output_path = Path(test_output_path)  # / f'{datetime.now():%Y-%m-%d_%H-%M-%S}'
        self.test_output_path.mkdir(parents=True, exist_ok=True)

    def setup(self, stage: str) -> None:
        super().setup(stage)

        if not self.metric_train:
            self.metric_train = HisDBIoU()
        if not self.metric_val:
            self.metric_val = HisDBIoU()
        if not self.metric_test:
            self.metric_test = HisDBIoU()

        if not hasattr(self.trainer.datamodule, 'get_img_name_coordinates'):
            raise NotImplementedError('DataModule needs to implement get_img_name_coordinates function')

        log.info("Setup done!")

    def forward(self, x):
        return self.model(x)

    @staticmethod
    def to_metrics_format(x: torch.Tensor) -> torch.Tensor:
        return _get_argmax(x)

    #############################################################################################
    ########################################### TRAIN ###########################################
    #############################################################################################
    def training_step(self, batch, batch_idx, **kwargs):
        input_batch, target_batch, mask_batch = batch
        metric_kwargs = {'hisdbiou': {'mask': mask_batch}}
        return super().training_step(batch=(input_batch, target_batch), batch_idx=batch_idx, metric_kwargs=metric_kwargs)

    #############################################################################################
    ############################################ VAL ############################################
    #############################################################################################

    def validation_step(self, batch, batch_idx, **kwargs):
        input_batch, target_batch, mask_batch = batch
        metric_kwargs = {'hisdbiou': {'mask': mask_batch}}
        return super().validation_step(batch=(input_batch, target_batch), batch_idx=batch_idx, metric_kwargs=metric_kwargs)

    #############################################################################################
    ########################################### TEST ############################################
    #############################################################################################

    def test_step(self, batch, batch_idx, **kwargs):
        input_batch, target_batch, mask_batch, input_idx = batch
        metric_kwargs = {'hisdbiou': {'mask': mask_batch}}
        output = super().test_step(batch=(input_batch, target_batch), batch_idx=batch_idx, metric_kwargs=metric_kwargs)

        if not hasattr(self.trainer.datamodule, 'get_img_name_coordinates'):
            raise NotImplementedError('Datamodule does not provide detailed information of the crop')

        for patch, idx in zip(output[OutputKeys.PREDICTION].data.detach().cpu().numpy(),
                              input_idx.detach().cpu().numpy()):
            patch_info = self.trainer.datamodule.get_img_name_coordinates(idx)
            img_name = patch_info[0]
            patch_name = patch_info[1]
            dest_folder = self.test_output_path / 'patches' / img_name
            dest_folder.mkdir(parents=True, exist_ok=True)
            dest_filename = dest_folder / f'{patch_name}.npy'

            np.save(file=str(dest_filename), arr=patch)

        return output
