package com.demo.ai;

import com.demo.ai.utils.VectorDistanceUtils;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Disabled;
import org.springframework.ai.document.Document;
import org.springframework.ai.openai.OpenAiEmbeddingModel;
import org.springframework.ai.reader.ExtractedTextFormatter;
import org.springframework.ai.reader.pdf.PagePdfDocumentReader;
import org.springframework.ai.reader.pdf.config.PdfDocumentReaderConfig;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.FileSystemResource;

import java.util.Arrays;
import java.util.List;

@SpringBootTest
@Disabled("Requires external model and local PDF; run manually for exploratory checks.")
public class TestVector {
    @Autowired
    private OpenAiEmbeddingModel embeddingModel;

    @Autowired
    private VectorStore vectorStore;

    @Test
    public void testVector(){

        String query = "国家级高温健康风险";

        String[] newsArray = new String[]{"厚植家国情怀 勇担历史使命",
                "日本7月5日大地震预言会成真吗",
                "山东舰抵达香港 甲板上停满舰载机",
                "高考志愿填报启动 网警继续护航",
                "武功山景区“吊带女孩福利”引争议",
                "“已有8艘船只驶往中国”",
                "首个国家级高温健康风险预警来了",
                "62岁地产大亨遭清华学霸儿子炮轰新",
                "B站高管“小姐姐”被逮捕",
                "家里真有矿也不敢报这个专业新"};
        float[] queryVector = embeddingModel.embed(query);//向量化
        double v0 = VectorDistanceUtils.euclideanDistance(queryVector, queryVector);
        System.out.println("v0 = " + v0);
        System.out.println(Arrays.toString(queryVector));
        List<float[]> newsVector = embeddingModel.embed(Arrays.asList(newsArray));
        for (float[] news : newsVector) {
            double v1 = VectorDistanceUtils.euclideanDistance(news, queryVector);
            System.out.println("v1 = " + v1);
        }
        for (float[] news : newsVector) {
            double v2 = VectorDistanceUtils.cosineDistance(queryVector, news);
            System.out.println("v2 = " + v2);
        }
    }


    @Test
    public void testPDF(){
        FileSystemResource resource = new FileSystemResource("中二知识笔记.pdf");
        PagePdfDocumentReader reader = new PagePdfDocumentReader(resource, PdfDocumentReaderConfig
                .builder()
                .withPageExtractedTextFormatter(ExtractedTextFormatter.defaults())
                .withPagesPerDocument(1)
                .build());
        List<Document> documents = reader.read();
        //System.out.println("documents = " + documents);

        vectorStore.add(documents);

        String query = "孔子及《论语》主要思想";

        List<Document> result = vectorStore.similaritySearch(SearchRequest.builder()
                .topK(1)
                .similarityThreshold(0.5)//阈值
                .filterExpression("file_name == '中二知识笔记.pdf'")
                .query(query).build());

        System.out.println("result = " + result);
    }

}
