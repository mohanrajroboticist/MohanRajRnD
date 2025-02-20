import torch
from torchvision.models import resnet18,mobilenet_v2
from torch.utils.data import random_split, DataLoader
import torchvision.transforms as transforms
import torchvision
from torch import nn
from helpers import get_model, test_one_epoch, get_brier_score, get_expected_calibration_error,plot_entropy_correct_incorrect
from helpers import get_accuracy_score,get_precision_score,get_recall_score,get_f1_score,get_classification_report,plot_confusion_matrix1
import os
import time
import copy
import random
import numpy as np
import pandas as pd
import neptune
import matplotlib.pyplot as plt
from helpers import get_multinomial_entropy,get_dirchlet_entropy,plot_calibration_curve
from data import import_data
from torch.quantization import quantize_fx
import warnings
warnings.filterwarnings("ignore")


def run_test():
    global accuracy_runs, precision_runs, recall_runs, f1_score_runs, ece_runs, brier_score_runs, time_elapsed_runs, auroc_runs

    data_dir = '../../data'
    save_path = '../results/'
    models_path = '../../results/'

    parameters = {  'num_classes': 10,
                    'batch_size': 1, 
                    'device': torch.device("cuda:0" if torch.cuda.is_available() else "cpu"),
                  
                    'dataset': "MNIST",
                    #'dataset': "CIFAR10", 
                  
                  
                    #'model_name':'LeNet',
                    #'model_name':'Resnet18',
                  
                    #'loss_function': 'Crossentropy',
                    #'loss_function':'Evidential_LOG',
                    #'loss_function':'Evidential_DIGAMMA',
                  
                  
                    'model_name':'LeNet_DUQ',
                    #'model_name':'ResNet_DUQ',
                    'loss_function': 'DUQ',
                  
                    'quantise': True}
    
    logger = False

    
    
    if parameters['quantise'] == True:
        model_path = str(models_path)+str(parameters['loss_function'])+'_'+str(parameters['model_name'])+'_quant_model.pth'
        condition_name = str(parameters['loss_function'])+'_'+str(parameters['model_name'])+'_quant'
        entropy_df_condition = str(parameters['loss_function'])+'-Quant'
        name = "Testing" + "-" + str(parameters['model_name']) + "-" + str(parameters['loss_function']) + "-" + "Quant"
        tags = [str(parameters['loss_function']),str(parameters['model_name']),str(parameters['dataset']),"Testing", "Quant"]
        parameters['device'] = "cpu"
    else:
        model_path = str(models_path)+str(parameters['loss_function'])+'_'+str(parameters['model_name'])+'_model.pth'
        condition_name = str(parameters['loss_function'])+'_'+str(parameters['model_name'])
        entropy_df_condition = str(parameters['loss_function'])
        name = "Testing" + "-" + str(parameters['model_name']) + "-" + str(parameters['loss_function'])
        tags = [str(parameters['loss_function']),str(parameters['model_name']),str(parameters['dataset']),"Testing"]
        parameters['device'] = "cpu"


    confusion_matrix_name = 'confusion_matrix_'+condition_name
    entropy_plot_name = 'entropy_'+condition_name
    calibration_plot_name = 'calibration_'+condition_name


    if logger and run_count==max_count:
        run = neptune.init_run(
        project="mohan20325145/FirstDraft",
        api_token="eyJhcGlfYWRkcmVzcyI6Imh0dHBzOi8vYXBwLm5lcHR1bmUuYWkiLCJhcGlfdXJsIjoiaHR0cHM6Ly9hcHAubmVwdHVuZS5haSIsImFwaV9rZXkiOiJhZWQyMTU4OC02NmU4LTRiNjgtYWE5Zi1lNDg5MjdmZGJhNzYifQ==",
        tags = tags,
        name= name,
        )
    else:
        run = None


    dataloader, class_names = import_data(parameters['dataset'], data_dir, parameters['batch_size'], parameters['batch_size'])
    test_loader = dataloader['val']
    device = parameters['device']
    model = get_model(parameters['model_name'],num_classes=parameters['num_classes'],weights=None)


    if parameters['quantise'] == True:
        dataiter = iter(dataloader['train'])
        images, labels = next(dataiter)
        print(images.shape)

        m = copy.deepcopy(model)
        m.to("cpu")
        m.eval()
        qconfig_dict = {"": torch.quantization.get_default_qconfig("fbgemm")}
        model_prepared = quantize_fx.prepare_fx(m, qconfig_dict, images)

        with torch.inference_mode():
            for _ in range(10):
                images, labels = next(dataiter)
                model_prepared(images)
        model = quantize_fx.convert_fx(model_prepared)
        print("Model quantised, q-weights need be updated")
        #print(model)
        #print('--------------')
        #model.print_readable()


    model.load_state_dict(torch.load(model_path))  
    #model = torch.load(model_path)
    model.eval()
    print("Loading trained weights and eval mode is successful")
    model.to(device=device)

    #print("Number of test images : ",len(test_loader.dataset))
    
    if run_count!=max_count:
        sample_to_test = 5000
    else:
        sample_to_test = 5000
        
    #random_indices = random.sample(range(len(test_loader.dataset)), sample_to_test)
    
    random_indices = [898]
    #random_indices = [898, 9709]
    #print(random_indices)
    random_samp_dataset = torch.utils.data.Subset(test_loader.dataset, random_indices)
    random_samp_dataloader = DataLoader(random_samp_dataset, batch_size=parameters['batch_size'], shuffle=False, num_workers=2)
    print("Number of test images : ",len(random_samp_dataloader.dataset))
    results = test_one_epoch(model=model,
                             dataloader=random_samp_dataloader,
                             num_classes=len(class_names),
                             device=device,
                             loss_function=parameters['loss_function'])

        
    
    
#     num_test_samples = len(test_loader.dataset)
#     split_lengths = [num_test_samples // 5] * 5
#     sliced_testdatasets = random_split(test_loader.dataset, split_lengths)
#     sliced_testloaders = [DataLoader(data, batch_size=parameters['batch_size'], shuffle=False, num_workers=2) for data in sliced_testdatasets]
    
#     results = test_one_epoch(model=model,
#                              dataloader=sliced_testloaders[run_count-1],
#                              num_classes=len(class_names),
#                              device=device,
#                              loss_function=parameters['loss_function'])

    # seperate the results
    true_labels = results['true_labels']
    pred_labels = results['pred_labels']
    probabilities = results['probabilities']
    model_output = results['model_output']
    time_elapsed = results['time_elapsed']
    auroc = results['auroc']
    

    # classification metrics
    accuracy_score = round(get_accuracy_score(true_labels=true_labels,predicted_labels=pred_labels),3)
    precision_score = round(get_precision_score(true_labels,pred_labels),3)
    recall_score = round(get_recall_score(true_labels,pred_labels),3)
    f1_score = round(get_f1_score(true_labels,pred_labels),3)
    #classification_report = get_classification_report(true_labels,pred_labels,class_names)
    confusion_mat_fig = plot_confusion_matrix1(true_labels=true_labels,
                                                predicted_labels=pred_labels,
                                                class_names=class_names,
                                                results_path=save_path,
                                                plot_name=confusion_matrix_name)
    print("Accuracy score : ", accuracy_score)
    print('--'*20)
    print("Precision score : ", precision_score)
    print('--'*20)
    print("Recall score : ", recall_score)
    print('--'*20)
    print("F1 score : ", f1_score)
    print('--'*20)
#     print("\nClassification report : ",classification_report)
#     print('--'*20)



    # Uncertainty metrics
    brier_score = get_brier_score(y_true=true_labels,y_pred_probs=probabilities)
    expected_calibration_error = get_expected_calibration_error(y_true=true_labels,y_pred=probabilities)
    calibration_curve_fig = plot_calibration_curve(y_prob=probabilities, y_true=true_labels, num_classes=parameters['num_classes'], save_path=save_path, file_name=calibration_plot_name)
    
    entropy_values = get_multinomial_entropy(probabilities)
    print("Brier Score : ", round(brier_score,5))
    print('--'*20)
    print("Expected calibration error : ", round(expected_calibration_error,5))
    print('--'*20)



    # Other metrics
    print("Inference time for ", true_labels.shape[0] ," image is : ", time_elapsed, "milliseconds")  

    if run_count!=max_count:
        accuracy_runs.extend([accuracy_score])
        precision_runs.extend([precision_score])
        recall_runs.extend([recall_score])
        f1_score_runs.extend([f1_score])
        ece_runs.extend([expected_calibration_error])
        brier_score_runs.extend([brier_score])
        time_elapsed_runs.extend([time_elapsed])
        auroc_runs.extend([auroc])
    
    if run_count==max_count:
        results_dict = {
            "entropy": entropy_values,
            "true_labels": true_labels,
            "pred_labels":pred_labels,
            "condition":entropy_df_condition,
            }
        results_df = pd.DataFrame(results_dict)
        results_df = results_df.astype({'entropy': 'float64'})
        results_df['is_prediction_correct'] = results_df['true_labels'] == results_df['pred_labels']
        results_df.to_csv(path_or_buf= save_path+condition_name+'_entropy.csv')      
        
        metrics_dict = {
            "accuracy":np.array(accuracy_runs),
            "precision":np.array(precision_runs),
            "recall_score":np.array(recall_runs),
            "f1score":np.array(f1_score_runs),
            "brierscore":np.array(brier_score_runs),
            "expectedcalibrationerror":np.array(ece_runs),
            "inferencetime":np.array(time_elapsed_runs),
            "auroc":np.array(auroc),
            }
        metrics_df = pd.DataFrame(metrics_dict)
        metrics_df.to_csv(path_or_buf= save_path+condition_name+'_metrics.csv')        
        

    #save model logits and probabilities as csv
    actual_labels = true_labels.reshape(-1, 1)
    logits_truelabel = np.concatenate((model_output, actual_labels), axis=1)
    logits_df = pd.DataFrame(logits_truelabel)
    logits_save_path = str(save_path)+str(condition_name)+'_logits.csv'
    #logits_df.to_csv(path_or_buf=logits_save_path)
    probo_df = pd.DataFrame(probabilities)
    probo_save_path = str(save_path)+str(condition_name)+'_probabilities.csv'
    #probo_df.to_csv(path_or_buf=probo_save_path)
    
    
    if run !=None:
        entropy_plot_fig = plot_entropy_correct_incorrect(data_df=results_df, save_path=save_path, file_name=entropy_plot_name)
        run['config/hyperparameters'] = parameters
        run['config/model'] = type(model).__name__
        run['metrics/accuracy'] = accuracy_score
        run['metrics/precision_score'] = precision_score
        run['metrics/recall_score'] = recall_score
        run['metrics/f1_score'] = f1_score
        run['metrics/brier_score'] = brier_score
        run['metrics/expected_calibration_error'] = expected_calibration_error
        run['metrics/classification_report'] = classification_report
        run['metrics/images/confusion_matrix'].upload(confusion_mat_fig)
        #run['metrics/images/entropy_correct_incorrect'].upload(entropy_plot_fig)
        run['metrics/images/calibration_plot'].upload(calibration_curve_fig)
    
    
    
    


accuracy_runs = []
precision_runs = []
recall_runs = []
f1_score_runs = []
ece_runs = []
brier_score_runs = []
time_elapsed_runs = []
auroc_runs = []


max_count=1
run_count=0
if __name__ == "__main__":
    for i in range(max_count):
        run_count += 1
        run_test()