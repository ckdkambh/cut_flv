from cut_flv import cut_file
import sys,os

time_length = 60*1000

def list_all_file(root_path):
    result = []
    ext_des = 'flv'
    list = os.listdir(root_path)
    for i in range(0,len(list)):
        path = os.path.join(root_path,list[i])
        #print('test ',path)
        if os.path.isfile(path) and (path.split('.')[-1] == ext_des):
            result.append(path)
    return result

def start_cuting(file_name):
    cut_file(file_name, 0, time_length)

def get_next_unuse_name(absfilename):
    cur_file_path = os.path.dirname(os.path.realpath(absfilename))
    if cur_file_path.find('result') == -1:
        tar_file_path = cur_file_path + '\\result\\'
    else:
        tar_file_path = cur_file_path + '\\'
    srcFileName, ext=os.path.splitext(absfilename) 
    srcFileName = srcFileName.split('\\')[-1]
    cut_index = srcFileName.find('_cut')
    if cut_index != -1:
        cur_num_str = srcFileName[cut_index + 4:]
        cur_num = int(cur_num_str)
        next_num = cur_num + 1
        next_num_str = str(next_num).zfill(3)
        return tar_file_path + srcFileName[:cut_index + 4]+next_num_str+ext
    else:
        return tar_file_path + srcFileName+'_cut001'+ext

if __name__ == '__main__':
    cur_file_path = os.path.dirname(os.path.realpath(__file__))
    file_list = list_all_file(cur_file_path)
    [start_cuting(x) for x in file_list]
    