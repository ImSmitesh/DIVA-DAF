from pathlib import Path
from typing import Optional, Callable, Union, Any

import numpy as np
import torch.nn as nn
import torch.optim
import torchmetrics

from src.datamodules.RGB.utils.output_tools import save_output_page_image
from src.datamodules.utils.misc import _get_argmax
from src.tasks.base_task import AbstractTask
from src.utils import utils
from src.tasks.utils.outputs import OutputKeys, reduce_dict

log = utils.get_logger(__name__)


class SemanticSegmentationFullPageRGB(AbstractTask):

    def __init__(self,
                 model: nn.Module,
                 optimizer: torch.optim.Optimizer,
                 loss_fn: Optional[Callable] = None,
                 metric_train: Optional[torchmetrics.Metric] = None,
                 metric_val: Optional[torchmetrics.Metric] = None,
                 metric_test: Optional[torchmetrics.Metric] = None,
                 test_output_path: Optional[Union[str, Path]] = 'test_output',
                 predict_output_path: Optional[Union[str, Path]] = 'predict_output',
                 confusion_matrix_val: Optional[bool] = False,
                 confusion_matrix_test: Optional[bool] = False,
                 confusion_matrix_log_every_n_epoch: Optional[int] = 1,
                 lr: float = 1e-3
                 ) -> None:
        """
        pixelvise semantic segmentation. The output of the network during test is a DIVAHisDB encoded image

        :param model: torch.nn.Module
            The encoder for the segmentation e.g. unet
        :param test_output_path: str
            String with a path to the output folder of the testing
        """
        super().__init__(
            model=model,
            optimizer=optimizer,
            loss_fn=loss_fn,
            metric_train=metric_train,
            metric_val=metric_val,
            metric_test=metric_test,
            test_output_path=test_output_path,
            predict_output_path=predict_output_path,
            lr=lr,
            confusion_matrix_val=confusion_matrix_val,
            confusion_matrix_test=confusion_matrix_test,
            confusion_matrix_log_every_n_epoch=confusion_matrix_log_every_n_epoch,
        )
        self.save_hyperparameters()

    def setup(self, stage: str) -> None:
        super().setup(stage)

        if not hasattr(self.trainer.datamodule, 'get_img_name'):
            raise NotImplementedError('DataModule needs to implement get_img_name function')

        log.info("Setup done!")

    def forward(self, x):
        return self.model(x)

    @staticmethod
    def to_metrics_format(x: torch.Tensor, **kwargs) -> torch.Tensor:
        return _get_argmax(x, **kwargs)

    #############################################################################################
    ########################################### TRAIN ###########################################
    #############################################################################################
    def training_step(self, batch, batch_idx, **kwargs):
        input_batch, target_batch = batch
        output = super().training_step(batch=(input_batch, target_batch), batch_idx=batch_idx)
        return reduce_dict(input_dict=output, key_list=[OutputKeys.LOSS])

    #############################################################################################
    ############################################ VAL ############################################
    #############################################################################################

    def validation_step(self, batch, batch_idx, **kwargs):
        input_batch, target_batch = batch
        output = super().validation_step(batch=(input_batch, target_batch), batch_idx=batch_idx)
        return reduce_dict(input_dict=output, key_list=[])

    #############################################################################################
    ########################################### TEST ############################################
    #############################################################################################

    def test_step(self, batch, batch_idx, **kwargs):
        input_batch, target_batch, input_idx = batch
        output = super().test_step(batch=(input_batch, target_batch), batch_idx=batch_idx)

        if not hasattr(self.trainer.datamodule, 'get_img_name'):
            raise NotImplementedError('Datamodule does not provide detailed information of the crop')

        for pred_raw, idx in zip(output[OutputKeys.PREDICTION].detach().cpu().numpy(),
                                 input_idx.detach().cpu().numpy()):
            patch_info = self.trainer.datamodule.get_img_name(idx)
            img_name = patch_info[0]
            dest_folder = self.test_output_path / 'pred_raw'
            dest_folder.mkdir(parents=True, exist_ok=True)
            dest_filename = dest_folder / f'{img_name}.npy'
            np.save(file=str(dest_filename), arr=pred_raw)

            dest_folder = self.test_output_path / 'pred'
            dest_folder.mkdir(parents=True, exist_ok=True)
            save_output_page_image(image_name=f'{img_name}.gif', output_image=pred_raw,
                                   output_folder=dest_folder, class_encoding=self.trainer.datamodule.class_encodings)

        return reduce_dict(input_dict=output, key_list=[])

    def on_test_end(self) -> None:
        pass

    #############################################################################################
    ######################################### PREDICT ###########################################
    #############################################################################################

    def predict_step(self, batch: Any, batch_idx: int, dataloader_idx: Optional[int] = None) -> Any:
        input_batch, input_idx = batch
        output = super().predict_step(batch=input_batch, batch_idx=batch_idx, dataloader_idx=dataloader_idx)

        if not hasattr(self.trainer.datamodule, 'get_img_name'):
            raise NotImplementedError('Datamodule does not provide detailed information of the crop')

        for pred_raw, idx in zip(output[OutputKeys.PREDICTION].detach().cpu().numpy(),
                                 input_idx.detach().cpu().numpy()):
            img_name = self.trainer.datamodule.get_img_name_prediction(idx)
            dest_folder = self.predict_output_path / 'pred_raw'
            dest_folder.mkdir(parents=True, exist_ok=True)
            dest_filename = dest_folder / f'{img_name}.npy'
            np.save(file=str(dest_filename), arr=pred_raw)

            dest_folder = self.predict_output_path / 'pred'
            dest_folder.mkdir(parents=True, exist_ok=True)
            save_output_page_image(image_name=f'{img_name}.gif', output_image=pred_raw,
                                   output_folder=dest_folder, class_encoding=self.trainer.datamodule.class_encodings)

        return reduce_dict(input_dict=output, key_list=[])
